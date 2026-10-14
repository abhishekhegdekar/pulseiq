"""Attendance summaries for people to read: departments, rolling 3-month and the December check.

Read-only. Uses the same calculations as pulseiq.attendance, so the numbers cannot disagree.
Run: docker compose run --rm load python -m pulseiq.attendance_report
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import pandas as pd

from pulseiq.attendance import (
    company_monthly, rolling_3_month, split_after_exit, suppress_small, add_metrics, SUM_COLS,
)

log = logging.getLogger("pulseiq.attendance_report")
RATES = ["attendance_rate", "late_rate", "paid_leave_share", "unpaid_absence_share", "wfh_share"]


def window_summary(att: pd.DataFrame, start: str, end: str, by: str = "department_id") -> pd.DataFrame:
    """Pooled metrics for one department over a fixed window (inclusive month-ends)."""
    w = att[(att.period_end_date >= start) & (att.period_end_date <= end)]
    sums = w.groupby(by)[SUM_COLS].sum()
    sums["employees"] = w.groupby(by)["employee_id"].nunique()
    return suppress_small(add_metrics(sums.reset_index()))


def december_check(att: pd.DataFrame) -> pd.DataFrame:
    """Company attendance rate for Nov 2025, Dec 2025 and Jan 2026 side by side."""
    m = company_monthly(att).set_index("period_end_date")
    rows = m.loc[pd.to_datetime(["2025-11-30", "2025-12-31", "2026-01-31"]), ["employees", *RATES]]
    rows.index = rows.index.strftime("%Y-%m")
    return rows


def main() -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(levelname)-7s %(message)s")
    clean = Path(os.environ.get("DATA_DIR", "data")) / "clean"
    att_all = pd.read_parquet(clean / "attendance.parquet")
    employee = pd.read_parquet(clean / "employee.parquet")
    dept = pd.read_parquet(clean / "department.parquet").set_index("department_id")["department_name"]
    att, _ = split_after_exit(att_all, employee)

    last = att.period_end_date.max()
    start = (last - pd.offsets.MonthEnd(11)).normalize()
    print(f"\nBy department, last 12 months ({start:%Y-%m} to {last:%Y-%m}), pooled; blank = fewer than 5 employees")
    t = window_summary(att, str(start.date()), str(last.date()))
    t.insert(1, "department", t.department_id.map(dept))
    print(t[["department_id", "department", "employees", *RATES]].to_string(index=False, na_rep="-",
          float_format=lambda v: f"{v:.4f}"))

    r = rolling_3_month(att)
    r = r[r.period_end_date == last].copy()
    r.insert(1, "department", r.department_id.map(dept))
    print(f"\nRolling 3 months to {last:%Y-%m}, by department:")
    print(r[["department_id", "department", "employees", "attendance_rate", "late_rate"]].to_string(
        index=False, na_rep="-", float_format=lambda v: f"{v:.4f}"))

    print("\nDecember check (company):")
    print(december_check(att).to_string(float_format=lambda v: f"{v:.4f}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
