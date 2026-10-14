"""Leave analysis: what kinds of leave are taken, by whom, and when it starts.

Read-only. Only Approved requests count as leave taken; other statuses are reported separately.
There is no daily attendance, so the weekday view is the weekday a leave STARTS (a proxy, not absence by weekday).
Run: docker compose run --rm --build load python -m pulseiq.leave_analysis
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from pulseiq.attendance import MIN_GROUP

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def by_status(lv: pd.DataFrame) -> pd.DataFrame:
    return lv.groupby("status").agg(requests=("leave_request_id", "count"), days=("days", "sum")).reset_index()


def approved(lv: pd.DataFrame, window_end: pd.Timestamp | None = None) -> pd.DataFrame:
    """Approved requests. With window_end, days after that date are cut off (pro-rated by working days),
    because a leave that runs past the last attendance month must not count against months we do not have."""
    a = lv[lv.status == "Approved"].copy()
    if window_end is not None:
        end = a.end_date.clip(upper=window_end)
        total = np.busday_count(a.start_date.values.astype("datetime64[D]"), (a.end_date + pd.Timedelta(days=1)).values.astype("datetime64[D]"))
        inside = np.busday_count(a.start_date.values.astype("datetime64[D]"), (end + pd.Timedelta(days=1)).values.astype("datetime64[D]"))
        a["days"] = a.days * np.where(total > 0, inside / np.maximum(total, 1), 1.0)
    return a


def by_type(lv: pd.DataFrame, types: pd.DataFrame, window_end: pd.Timestamp | None = None) -> pd.DataFrame:
    a = approved(lv, window_end)
    t = a.groupby("leave_type_code").agg(requests=("leave_request_id", "count"), days=("days", "sum"),
                                         employees=("employee_id", "nunique")).reset_index()
    t["avg_days_per_request"] = t.days / t.requests
    t = t.merge(types[["leave_type_code", "leave_type_name", "pay_type"]], on="leave_type_code", how="left")
    return t.sort_values("days", ascending=False)[
        ["leave_type_code", "leave_type_name", "pay_type", "requests", "employees", "days", "avg_days_per_request"]]


def start_weekday(lv: pd.DataFrame) -> pd.DataFrame:
    a = approved(lv)
    a = a[a.leave_type_code != "ML"]  # long statutory leave would swamp a weekday pattern
    n = a.groupby(a.start_date.dt.dayofweek).size().reindex(range(7), fill_value=0)
    return pd.DataFrame({"weekday": WEEKDAYS, "leave_starts": n.values, "share": (n / n.sum()).values})


def dept_leave(lv: pd.DataFrame, att: pd.DataFrame, employee: pd.DataFrame, window_end: pd.Timestamp | None = None) -> pd.DataFrame:
    """Approved leave days per person-month (scheduled days / ~21) by department, with and without maternity."""
    a = approved(lv, window_end).merge(employee[["employee_id", "department_id"]].drop_duplicates("employee_id"), on="employee_id")
    g = att.groupby("department_id").agg(employees=("employee_id", "nunique"), emp_months=("employee_id", "size"))
    all_days = a.groupby("department_id").days.sum()
    no_ml = a[a.leave_type_code != "ML"].groupby("department_id").days.sum()
    out = g.join(all_days.rename("approved_days")).join(no_ml.rename("days_excl_maternity")).fillna(0)
    out["days_per_emp_month"] = out.approved_days / out.emp_months
    out["excl_maternity"] = out.days_excl_maternity / out.emp_months
    out.loc[out.employees < MIN_GROUP, ["approved_days", "days_excl_maternity", "days_per_emp_month", "excl_maternity"]] = pd.NA
    return out.reset_index()


def main() -> int:
    clean = Path(os.environ.get("DATA_DIR", "data")) / "clean"
    lv = pd.read_parquet(clean / "leave.parquet")
    types = pd.read_parquet(clean / "leave_type.parquet")
    att = pd.read_parquet(clean / "attendance.parquet")
    employee = pd.read_parquet(clean / "employee.parquet")
    window_end = att.period_end_date.max()
    dept = pd.read_parquet(clean / "department.parquet").set_index("department_id")["department_name"]
    f = lambda v: f"{v:.3f}"
    print(f"\nLeave requests by status ({len(lv)} clean rows); only Approved counts as leave taken:")
    print(by_status(lv).to_string(index=False))
    print(f"\nApproved leave by type (days after {window_end:%Y-%m-%d} cut off):")
    print(by_type(lv, types, window_end).to_string(index=False, float_format=lambda v: f"{v:.2f}"))
    print("\nApproved leave starts by weekday (maternity excluded; proxy only):")
    print(start_weekday(lv).to_string(index=False, float_format=f))
    d = dept_leave(lv, att, employee, window_end)
    d.insert(1, "department", d.department_id.map(dept))
    print("\nApproved leave days per employee-month, by department (blank = under 5 employees):")
    print(d[["department_id", "department", "employees", "days_per_emp_month", "excl_maternity"]].to_string(
        index=False, na_rep="-", float_format=f))
    return 0


if __name__ == "__main__":
    sys.exit(main())
