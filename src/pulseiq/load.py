"""Load the clean Parquet files into PostgreSQL with upserts.

Run:  python -m pulseiq.load        (or: docker compose run --rm load)

Rules
- One transaction: either every table is loaded or nothing is.
- Upsert on each table's primary key: new rows are inserted, changed rows are updated,
  identical rows are left alone. Running the load twice therefore changes nothing.
- Nothing is ever deleted. SCD2 history stays; a row that disappears from the source
  is reported (not removed).
"""
import logging
import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import psycopg
from psycopg import sql

from pulseiq.config import _require
from pulseiq.errors import ConfigError, PulseIQError

log = logging.getLogger("pulseiq.load")

# (clean file, table, primary key) in dependency order: parents before children.
LOAD_ORDER = [
    ("department", "dim_department", ["department_id"]),
    ("leave_type", "dim_leave_type", ["leave_type_code"]),
    ("date", "dim_date", ["date_key"]),
    ("role", "dim_role", ["role_id"]),
    ("employee", "dim_employee", ["employee_key"]),
    ("payroll", "fact_payroll", ["employee_key", "run_id"]),
    ("attendance", "fact_attendance_monthly", ["employee_key", "date_key"]),
    ("leave", "fact_leave", ["leave_request_id"]),
]


def rows_from_frame(df: pd.DataFrame, columns: list[str]) -> list[tuple]:
    """Turn a DataFrame into plain Python rows: NaN/NaT -> None, Timestamp -> date."""
    series = []
    for col in columns:
        s = df[col]
        if pd.api.types.is_datetime64_any_dtype(s):
            values = [None if pd.isna(x) else x.date() for x in s]
        else:
            values = [None if pd.isna(x) else x for x in s.tolist()]
        series.append(values)
    return list(zip(*series)) if series else []


def _db_settings() -> dict:
    missing = [n for n in ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")
               if not os.environ.get(n, "").strip()]
    if missing:
        raise ConfigError(f"Environment variable(s) not set: {', '.join(missing)}")
    return dict(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


def _table_columns(cur, table: str) -> list[str]:
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position",
        (table,))
    return [r[0] for r in cur.fetchall()]


def upsert_table(cur, table: str, key: list[str], df: pd.DataFrame) -> dict:
    columns = _table_columns(cur, table)
    absent = [c for c in columns if c not in df.columns]
    if absent:
        raise ConfigError(f"{table}: clean file is missing column(s) {absent}")
    non_key = [c for c in columns if c not in key]

    ident = sql.Identifier
    cols = sql.SQL(", ").join(map(ident, columns))

    cur.execute(sql.SQL("DROP TABLE IF EXISTS pg_temp.stage"))
    cur.execute(sql.SQL("CREATE TEMP TABLE stage (LIKE {} INCLUDING DEFAULTS)").format(ident(table)))
    with cur.copy(sql.SQL("COPY stage ({}) FROM STDIN").format(cols)) as copy:
        for row in rows_from_frame(df, columns):
            copy.write_row(row)

    # Only touch rows that are new or really different (IS DISTINCT FROM is NULL-safe).
    set_clause = sql.SQL(", ").join(
        sql.SQL("{c} = EXCLUDED.{c}").format(c=ident(c)) for c in non_key)
    old = sql.SQL(", ").join(sql.SQL("{}.{}").format(ident(table), ident(c)) for c in non_key)
    new = sql.SQL(", ").join(sql.SQL("EXCLUDED.{}").format(ident(c)) for c in non_key)
    query = sql.SQL(
        "INSERT INTO {t} ({cols}) SELECT {cols} FROM stage "
        "ON CONFLICT ({key}) DO UPDATE SET {set} WHERE ({old}) IS DISTINCT FROM ({new}) "
        "RETURNING (xmax = 0)"
    ).format(t=ident(table), cols=cols, key=sql.SQL(", ").join(map(ident, key)),
             set=set_clause, old=old, new=new)
    cur.execute(query)
    flags = [r[0] for r in cur.fetchall()]
    inserted = sum(flags)
    updated = len(flags) - inserted

    # Rows already in the table that are no longer in the source: reported, never deleted.
    cur.execute(sql.SQL("SELECT count(*) FROM {t} WHERE ({key}) NOT IN (SELECT {key} FROM stage)")
                .format(t=ident(table), key=sql.SQL(", ").join(map(ident, key))))
    not_in_source = cur.fetchone()[0]
    cur.execute(sql.SQL("DROP TABLE pg_temp.stage"))
    return {"rows_in_file": len(df), "inserted": inserted, "updated": updated,
            "unchanged": len(df) - len(flags), "not_in_source": not_in_source}


# One row per employee per month-end while employed. Rules (docs/warehouse-schema.md):
#  - employed at month end: hire_date <= month end and (no exit_date or exit_date > month end)
#  - department/role come from the latest version with valid_from <= month end (as-of rule)
HEADCOUNT_SQL = """
WITH person AS (
    SELECT employee_id, min(hire_date) AS hire_date, max(exit_date) AS exit_date
    FROM dim_employee GROUP BY employee_id
)
SELECT DISTINCT ON (e.employee_id, d.date)
       d.date AS month_end_date, e.employee_id, e.employee_key, e.department_id, e.role_id
FROM dim_date d
JOIN person p ON p.hire_date <= d.date AND (p.exit_date IS NULL OR p.exit_date > d.date)
JOIN dim_employee e ON e.employee_id = p.employee_id AND e.valid_from <= d.date
WHERE d.is_month_end = 'Y' AND d.date <= %(reporting_date)s
ORDER BY e.employee_id, d.date, e.valid_from DESC
"""


def build_headcount(cur, reporting_date: date) -> dict:
    """Rebuild fact_headcount_monthly from dim_employee. Fully determined by the
    dimensions, so rows that no longer belong are deleted (this table only)."""
    cur.execute("DROP TABLE IF EXISTS pg_temp.hc_new")
    cur.execute("CREATE TEMP TABLE hc_new AS " + HEADCOUNT_SQL, {"reporting_date": reporting_date})
    cur.execute("SELECT count(*) FROM hc_new")
    built = cur.fetchone()[0]
    cur.execute(
        "DELETE FROM fact_headcount_monthly h WHERE NOT EXISTS ("
        "SELECT 1 FROM hc_new n WHERE n.employee_id = h.employee_id "
        "AND n.month_end_date = h.month_end_date)")
    deleted = cur.rowcount
    cur.execute(
        "INSERT INTO fact_headcount_monthly (month_end_date, employee_id, employee_key, department_id, role_id) "
        "SELECT month_end_date, employee_id, employee_key, department_id, role_id FROM hc_new "
        "ON CONFLICT (employee_id, month_end_date) DO UPDATE SET "
        "employee_key = EXCLUDED.employee_key, department_id = EXCLUDED.department_id, "
        "role_id = EXCLUDED.role_id "
        "WHERE (fact_headcount_monthly.employee_key, fact_headcount_monthly.department_id, "
        "fact_headcount_monthly.role_id) IS DISTINCT FROM "
        "(EXCLUDED.employee_key, EXCLUDED.department_id, EXCLUDED.role_id) "
        "RETURNING (xmax = 0)")
    flags = [r[0] for r in cur.fetchall()]
    cur.execute("DROP TABLE pg_temp.hc_new")
    return {"rows_in_file": built, "inserted": sum(flags), "updated": len(flags) - sum(flags),
            "unchanged": built - len(flags), "not_in_source": 0, "deleted": deleted}


ANOMALY_SOURCE = "attendance_monthly_features"
ANOMALY_COLUMNS = ["result_id", "record_id", "employee_id", "period_end_date", "anomaly_score", "flagged",
                   "reason_code", "reason_text", "model_version", "scored_date"]


def anomaly_frame(workbook: Path) -> pd.DataFrame:
    """Attendance rows of the AI/ML team's sheet fact_anomaly, shaped for fact_anomaly_attendance."""
    a = pd.read_excel(workbook, sheet_name="fact_anomaly")
    a = a[a["source_dataset"] == ANOMALY_SOURCE].copy()
    a["period_end_date"] = pd.to_datetime(a["period"]) + pd.offsets.MonthEnd(0)
    a["scored_date"] = pd.to_datetime(a["scored_at"]).dt.normalize()
    return a[ANOMALY_COLUMNS].reset_index(drop=True)


def load_all(clean_dir: Path, schema_file: Path, settings: dict, reporting_date: date,
             views_file: Path | None = None, attendance_sql: Path | None = None,
             anomaly_workbook: Path | None = None) -> dict:
    frames = {}
    for name, _, _ in LOAD_ORDER:
        path = clean_dir / f"{name}.parquet"
        if not path.exists():
            raise ConfigError(f"Missing clean file {path}. Run the ETL first.")
        frames[name] = pd.read_parquet(path)

    results = {}
    with psycopg.connect(**settings) as conn:      # commits on success, rolls back on error
        with conn.cursor() as cur:
            cur.execute(schema_file.read_text(encoding="utf-8"))   # idempotent
            if views_file is not None:                             # dashboard views, also idempotent
                cur.execute(views_file.read_text(encoding="utf-8"))
            if attendance_sql is not None:                         # anomaly table + attendance views
                cur.execute(attendance_sql.read_text(encoding="utf-8"))
            for name, table, key in LOAD_ORDER:
                results[table] = upsert_table(cur, table, key, frames[name])
                log.info("Loaded %-22s %s", table, results[table])
            if anomaly_workbook is not None:
                results["fact_anomaly_attendance"] = upsert_table(
                    cur, "fact_anomaly_attendance", ["result_id"], anomaly_frame(anomaly_workbook))
                log.info("Loaded %-22s %s", "fact_anomaly_attendance", results["fact_anomaly_attendance"])
            results["fact_headcount_monthly"] = build_headcount(cur, reporting_date)
            log.info("Built  %-22s %s", "fact_headcount_monthly", results["fact_headcount_monthly"])
    return results


def main() -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    try:
        settings = _db_settings()
        data_dir = Path(os.environ.get("DATA_DIR", "data"))
        schema_file = Path(os.environ.get("SCHEMA_FILE", "sql/01_schema.sql"))
        views_file = Path(os.environ.get("VIEWS_FILE", "sql/02_reporting_views.sql"))
        attendance_sql = Path(os.environ.get("ATTENDANCE_SQL_FILE", "sql/03_attendance_reporting.sql"))
        for needed in (schema_file, views_file, attendance_sql):
            if not needed.exists():
                raise ConfigError(f"SQL file not found: {needed}")
        raw_date = _require("REPORTING_DATE")
        try:
            reporting_date = date.fromisoformat(raw_date)
        except ValueError:
            raise ConfigError(f"REPORTING_DATE must be YYYY-MM-DD, got {raw_date!r}") from None
        workbook = Path(os.environ.get("INPUT_WORKBOOK", ""))
        if not workbook.is_file():
            log.warning("INPUT_WORKBOOK not found: anomaly flags are not loaded")
            workbook = None
        results = load_all(data_dir / "clean", schema_file, settings, reporting_date, views_file,
                           attendance_sql, workbook)
    except PulseIQError as exc:
        log.error("STATUS=FAILED_CONFIG: %s", exc)
        return 2
    except Exception:
        log.exception("STATUS=FAILED_UNEXPECTED (nothing was committed)")
        return 3
    totals = {k: sum(r.get(k, 0) for r in results.values())
              for k in ("rows_in_file", "inserted", "updated", "unchanged", "not_in_source", "deleted")}
    log.info("Totals: %s", totals)
    log.info("STATUS=SUCCESS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
