"""Check the warehouse headcount against the workbook's own fact_headcount_monthly sheet.

Run:  docker compose run --rm load python -m pulseiq.check_headcount
Compares headcount_end per department per month. Exit 0 = identical, 1 = differences.
"""
import logging
import os
import sys

import pandas as pd
import psycopg

from pulseiq.config import _require
from pulseiq.errors import ConfigError, PulseIQError
from pulseiq.load import _db_settings

log = logging.getLogger("pulseiq.check")


def compare(sheet: pd.DataFrame, db: pd.DataFrame) -> pd.DataFrame:
    """Return the (month, department) rows where the two sides disagree; missing counts as 0."""
    left = sheet[["month_end_date", "department_id", "headcount_end"]]
    both = left.merge(db, on=["month_end_date", "department_id"], how="outer")
    both[["headcount_end", "warehouse"]] = both[["headcount_end", "warehouse"]].fillna(0).astype(int)
    return both[both["headcount_end"] != both["warehouse"]].sort_values(["month_end_date", "department_id"])


def main() -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    try:
        workbook = _require("INPUT_WORKBOOK")
        settings = _db_settings()
        if not os.path.exists(workbook):
            raise ConfigError(f"Workbook not found: {workbook}")
        sheet = pd.read_excel(workbook, sheet_name="fact_headcount_monthly")
        sheet["month_end_date"] = pd.to_datetime(sheet["date_key"].astype(str), format="%Y%m%d").dt.date
        with psycopg.connect(**settings) as conn, conn.cursor() as cur:
            cur.execute("SELECT month_end_date, department_id, count(DISTINCT employee_id)::int AS warehouse "
                        "FROM fact_headcount_monthly GROUP BY 1, 2")
            db = pd.DataFrame(cur.fetchall(), columns=["month_end_date", "department_id", "warehouse"])
            # Employees who are employed at a month end but have no version yet (should be 0).
            cur.execute("SELECT count(*) FROM dim_date d JOIN (SELECT employee_id, min(hire_date) h, "
                        "max(exit_date) x, min(valid_from) v FROM dim_employee GROUP BY 1) p "
                        "ON p.h <= d.date AND (p.x IS NULL OR p.x > d.date) AND p.v > d.date "
                        "WHERE d.is_month_end = 'Y'")
            no_version = cur.fetchone()[0]
    except PulseIQError as exc:
        log.error("STATUS=FAILED_CONFIG: %s", exc)
        return 2
    except Exception:
        log.exception("STATUS=FAILED_UNEXPECTED")
        return 3
    diff = compare(sheet, db)
    log.info("Compared %d department-months; workbook total=%d, warehouse total=%d",
             len(sheet), int(sheet["headcount_end"].sum()), int(db["warehouse"].sum()))
    log.info("Employed at a month end but without a version: %d", no_version)
    if len(diff) or no_version:
        log.error("STATUS=MISMATCH: %d department-month(s) differ\n%s", len(diff), diff.head(20).to_string(index=False))
        return 1
    log.info("STATUS=MATCH: headcount agrees with the workbook for every department and month")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
