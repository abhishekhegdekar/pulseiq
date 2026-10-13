"""Run the warehouse SQL answers (sql/q1..q4) and compare them with numbers computed
independently in pandas from the clean Parquet files.

Run:  docker compose run --rm load python -m pulseiq.check_answers
Exit 0 = every answer agrees, 1 = a difference, 2 = config problem, 3 = unexpected error.
"""
import logging
import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import psycopg

from pulseiq.errors import ConfigError, PulseIQError
from pulseiq.load import _db_settings

log = logging.getLogger("pulseiq.answers")

HEADCOUNT_DATE = pd.Timestamp("2026-09-30")
COST_MONTHS = [(2026, 5), (2026, 6), (2026, 7)]
ATTENDANCE_MONTH = (2026, 9)


def expected_q1(employee: pd.DataFrame) -> pd.DataFrame:
    person = employee.groupby("employee_id").agg(hire=("hire_date", "min"), exit=("exit_date", "max"))
    employed = person[(person.hire <= HEADCOUNT_DATE) & (person["exit"].isna() | (person["exit"] > HEADCOUNT_DATE))]
    versions = employee[employee.valid_from <= HEADCOUNT_DATE].sort_values("valid_from")
    latest = versions.groupby("employee_id").tail(1).set_index("employee_id")
    dept = latest.loc[latest.index.intersection(employed.index), "department_id"]
    return dept.value_counts().rename("headcount").rename_axis("department_id").reset_index() \
        .sort_values("department_id").reset_index(drop=True)


def expected_q2(payroll: pd.DataFrame) -> pd.DataFrame:
    keep = payroll[[(y, m) in COST_MONTHS for y, m in zip(payroll.period_year, payroll.period_month)]]
    out = keep.groupby(["period_year", "period_month", "department_id"]).agg(
        employees_paid=("employee_id", "nunique"), employer_cost=("employer_cost", "sum")).reset_index()
    out["year_month"] = out.period_year.astype(str) + "-" + out.period_month.astype(str).str.zfill(2)
    return out[["year_month", "department_id", "employees_paid", "employer_cost"]] \
        .sort_values(["year_month", "department_id"]).reset_index(drop=True)


def expected_q3(attendance: pd.DataFrame, payroll: pd.DataFrame) -> pd.DataFrame:
    y, m = ATTENDANCE_MONTH
    a = attendance[(attendance.period_year == y) & (attendance.period_month == m)]
    g = a.groupby("department_id").agg(employees=("employee_id", "nunique"), sched=("scheduled_days", "sum"),
                                       present=("present_days", "sum"), half=("half_days_unpaid", "sum"))
    g["attendance_rate"] = (g.present + 0.5 * g.half) / g.sched
    p = payroll[(payroll.period_year == y) & (payroll.period_month == m)]
    g["lop_days"] = p.groupby("department_id").lop_days.sum().reindex(g.index).fillna(0)
    return g.reset_index()[["department_id", "employees", "attendance_rate", "lop_days"]]


def _run_sql(cur, path: Path) -> pd.DataFrame:
    cur.execute(path.read_text(encoding="utf-8"))
    cols = [c.name for c in cur.description]
    return pd.DataFrame(cur.fetchall(), columns=cols)


def _same(got: pd.DataFrame, want: pd.DataFrame, keys: list[str], numeric: dict[str, float]) -> list[str]:
    """Return a list of problems; empty means identical (numbers within the given tolerance)."""
    merged = got.merge(want, on=keys, how="outer", suffixes=("_sql", "_pandas"), indicator=True)
    problems = [f"row only in {side}: {dict(r[keys])}" for side, name in (("SQL", "left_only"), ("pandas", "right_only"))
                for _, r in merged[merged["_merge"] == name].iterrows()]
    both = merged[merged["_merge"] == "both"]
    for col, tol in numeric.items():
        bad = both[(both[f"{col}_sql"].astype(float) - both[f"{col}_pandas"].astype(float)).abs() > tol]
        problems += [f"{col} differs for {dict(r[keys])}: sql={r[f'{col}_sql']} pandas={r[f'{col}_pandas']}"
                     for _, r in bad.iterrows()]
    return problems


def main() -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    try:
        settings = _db_settings()
        clean = Path(os.environ.get("DATA_DIR", "data")) / "clean"
        sql_dir = Path(os.environ.get("SQL_DIR", "sql"))
        for name in ("employee", "payroll", "attendance"):
            if not (clean / f"{name}.parquet").exists():
                raise ConfigError(f"Missing clean file {clean / (name + '.parquet')}")
        employee = pd.read_parquet(clean / "employee.parquet")
        payroll = pd.read_parquet(clean / "payroll.parquet")
        attendance = pd.read_parquet(clean / "attendance.parquet")
        with psycopg.connect(**settings) as conn, conn.cursor() as cur:
            q1 = _run_sql(cur, sql_dir / "q1_headcount_by_department.sql")
            q2 = _run_sql(cur, sql_dir / "q2_employer_cost_by_department_month.sql")
            q3 = _run_sql(cur, sql_dir / "q3_attendance_and_lop_by_department.sql")
            q4 = _run_sql(cur, sql_dir / "q4_facts_link_to_effective_version.sql")
    except PulseIQError as exc:
        log.error("STATUS=FAILED_CONFIG: %s", exc)
        return 2
    except Exception:
        log.exception("STATUS=FAILED_UNEXPECTED")
        return 3

    checks = {
        "Q1 headcount by department (30 Sep 2026)":
            (len(q1), _same(q1, expected_q1(employee), ["department_id"], {"headcount": 0})),
        "Q2 employer cost by department, May-Jul 2026":
            (len(q2), _same(q2, expected_q2(payroll), ["year_month", "department_id"],
                            {"employees_paid": 0, "employer_cost": 0.011})),
        "Q3 attendance rate and LOP days, Sep 2026":
            (len(q3), _same(q3, expected_q3(attendance, payroll), ["department_id"],
                            {"employees": 0, "attendance_rate": 0.00006, "lop_days": 0.001})),
    }
    q4_problems = [f"{r.fact}: key_differs={r.key_differs} attrs_differ={r.attrs_differ}"
                   for r in q4.itertuples() if r.key_differs or r.attrs_differ]
    checks["Q4 facts link to the effective employee version"] = (int(q4.fact_rows.sum()), q4_problems)

    failed = 0
    for label, (rows, problems) in checks.items():
        if problems:
            failed += 1
            log.error("MISMATCH  %s (%d rows)\n  %s", label, rows, "\n  ".join(problems[:10]))
        else:
            log.info("MATCH     %s (%d rows)", label, rows)
    log.info("Q1 total headcount = %d", int(q1.headcount.sum()))
    log.info("STATUS=%s", "ALL_MATCH" if not failed else f"{failed}_MISMATCH")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
