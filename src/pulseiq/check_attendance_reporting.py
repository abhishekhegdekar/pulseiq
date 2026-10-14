"""Check the attendance views (schema 'reporting') against the Python results from the clean files.

Run:  docker compose run --rm --build load python -m pulseiq.check_attendance_reporting
Exit 0 = everything agrees, 1 = a difference, 2 = config problem, 3 = unexpected error.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import pandas as pd
import psycopg

from pulseiq.anomaly_review import join_flags, load_flags, supported
from pulseiq.attendance import MIN_GROUP, SUM_COLS, rolling_3_month, split_after_exit, summarise
from pulseiq.check_reporting import _q, diff
from pulseiq.errors import ConfigError, PulseIQError
from pulseiq.leave_analysis import approved, start_weekday
from pulseiq.load import _db_settings

log = logging.getLogger("pulseiq.check_attendance_reporting")
CHECK_LABEL = {True: "Confirmed", False: "Contradicted"}


def expected_monthly(att: pd.DataFrame) -> pd.DataFrame:
    t = summarise(att, ["department_id", "period_end_date"])
    t = t[t.employees >= MIN_GROUP]
    return t.assign(month_end_date=t.period_end_date.dt.date)[["month_end_date", "department_id", "employees", *SUM_COLS]]


def expected_rolling(att: pd.DataFrame) -> pd.DataFrame:
    r = rolling_3_month(att).dropna(subset=SUM_COLS)
    r = r[r.employees >= MIN_GROUP]
    r = r.assign(month_end_date=r.period_end_date.dt.date).rename(columns={c: f"r_{c}" for c in SUM_COLS})
    return r[["month_end_date", "department_id", *[f"r_{c}" for c in SUM_COLS]]]


def expected_leave(lv: pd.DataFrame, window_end: pd.Timestamp) -> pd.DataFrame:
    """Requests, employees and in-window days per leave type and status, cells under MIN_GROUP employees removed.
    Uses the same proration as leave_analysis.approved (weekdays up to the last attendance month)."""
    base = lv.assign(status_keep=lv.status)
    parts = []
    for status, g in base.groupby("status"):
        g = g.copy()
        g["status"] = "Approved"          # reuse approved() for the proration only
        parts.append(approved(g, window_end).assign(status=status))
    d = pd.concat(parts)
    out = d.groupby(["leave_type_code", "status"]).agg(
        requests=("leave_request_id", "count"), employees=("employee_id", "nunique"), days=("days", "sum")).reset_index()
    out["days"] = out["days"].round(1)
    return out[out.employees >= MIN_GROUP]


def expected_flags(flags: pd.DataFrame, att: pd.DataFrame, kept: set) -> pd.DataFrame:
    j = join_flags(flags, att)
    j = j[[(m, d) in kept for m, d in zip(j.month.dt.date, j.department_id)]]
    j["monthly_data_check"] = [CHECK_LABEL.get(supported(r), "Not checkable") for _, r in j.iterrows()]
    return j.groupby(["reason_code", "monthly_data_check"]).size().rename("n").reset_index()


def main() -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    try:
        settings = _db_settings()
        data = Path(os.environ.get("DATA_DIR", "data")) / "clean"
        workbook = Path(os.environ.get("INPUT_WORKBOOK", ""))
        for needed in (data / "attendance.parquet", data / "employee.parquet", data / "leave.parquet",
                       data / "leave_type.parquet", workbook):
            if not needed.is_file():
                raise ConfigError(f"Not found: {needed}")
        att_all = pd.read_parquet(data / "attendance.parquet")
        employee = pd.read_parquet(data / "employee.parquet")
        lv = pd.read_parquet(data / "leave.parquet")
        types = pd.read_parquet(data / "leave_type.parquet")
        flags = load_flags(workbook)
        with psycopg.connect(**settings) as conn, conn.cursor() as cur:
            am = _q(cur, "SELECT * FROM reporting.attendance_monthly")
            lt = _q(cur, "SELECT * FROM reporting.leave_by_type")
            wd = _q(cur, "SELECT * FROM reporting.leave_start_weekday")
            fm = _q(cur, "SELECT * FROM reporting.attendance_flags_monthly")
            rl = _q(cur, "SELECT * FROM reporting.attendance_rolling_3m")
            n_flags = _q(cur, "SELECT count(*) AS n FROM fact_anomaly_attendance").n[0]
    except PulseIQError as exc:
        log.error("STATUS=FAILED_CONFIG: %s", exc)
        return 2
    except Exception:
        log.exception("STATUS=FAILED_UNEXPECTED")
        return 3

    att, _ = split_after_exit(att_all, employee)
    window_end = att.period_end_date.max()
    checks = {}
    exp = expected_monthly(att)
    checks["B1 monthly day counts by department, all months"] = diff(
        am, exp, ["month_end_date", "department_id"], ["employees", *SUM_COLS])

    missing = set(att.department_id) - set(am.department_id)
    p2 = [] if missing == {"D00"} else [f"departments missing from the view: {sorted(missing)}"]
    checks["B2 only the Executive Office (under 5 employees) is left out"] = p2

    p3 = diff(lt.assign(days=lt.days.astype(float))[["leave_type_code", "status", "requests", "employees", "days"]],
              expected_leave(lv, window_end), ["leave_type_code", "status"], ["requests", "employees", "days"])
    checks["B3 leave by type and status (days cut at the last attendance month; cells under 5 employees left out)"] = p3

    w = start_weekday(lv).iloc[:5].assign(weekday_number=range(1, 6))[["weekday_number", "leave_starts"]]
    checks["B4 approved leave starts by weekday"] = diff(wd[["weekday_number", "leave_starts"]], w, ["weekday_number"], ["leave_starts"])

    kept = set(zip(am.month_end_date, am.department_id))
    ef = expected_flags(flags, att_all, kept)
    gf = fm.groupby(["reason_code", "monthly_data_check"]).flagged_employee_months.sum().rename("n").reset_index()
    p5 = diff(gf, ef, ["reason_code", "monthly_data_check"], ["n"])
    if n_flags != len(flags):
        p5.append(f"flags in the warehouse={n_flags} sheet={len(flags)}")
    checks["B5 anomaly flags by reason and check result"] = p5

    rcols = [f"r_{c}" for c in SUM_COLS]
    checks["B6 pooled rolling 3 months by department"] = diff(
        rl, expected_rolling(att), ["month_end_date", "department_id"], rcols)

    failed = 0
    for label, problems in checks.items():
        if problems:
            failed += 1
            log.error("MISMATCH  %s\n  %s", label, "\n  ".join(problems[:10]))
        else:
            log.info("MATCH     %s", label)
    log.info("Rows: attendance_monthly=%d, rolling_3m=%d, leave_by_type=%d, flags=%d", len(am), len(rl), len(lt), int(fm.flagged_employee_months.sum()))
    log.info("STATUS=%s", "ALL_MATCH" if not failed else f"{failed}_MISMATCH")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
