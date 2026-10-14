"""Attendance analysis (Task 4): pooled rates, small-group rule, rolling average and reconciliation checks.

Definitions live in docs/attendance_definitions.md. This module works on the clean Parquet files, in pandas,
so it is an independent route to the numbers that the SQL views will later be compared with.

Run:  docker compose run --rm load python -m pulseiq.attendance
Exit 0 = every check passed, 1 = a check failed, 2 = config problem, 3 = unexpected error.
"""
import logging
import os
import sys
from pathlib import Path

import pandas as pd

from pulseiq.errors import ConfigError, PulseIQError

log = logging.getLogger("pulseiq.attendance")

MIN_GROUP = 5          # minimum employees in a group and month before a rate is shown
RATE_TOLERANCE = 0.0001
SUM_COLS = ["scheduled_days", "present_days", "wfh_days", "half_days_unpaid", "paid_leave_days",
            "unpaid_absence_days", "late_arrivals"]
METRIC_COLS = ["attendance_rate", "late_rate", "paid_leave_share", "unpaid_absence_share", "wfh_share"]


def split_after_exit(att: pd.DataFrame, employee: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Separate rows recorded for a month after the employee's exit month (known issue DQ-01)."""
    exit_month_end = employee.groupby("employee_id").exit_date.max() + pd.offsets.MonthEnd(0)
    after = att.period_end_date > att.employee_id.map(exit_month_end)
    return att[~after].copy(), att[after].copy()


def add_metrics(sums: pd.DataFrame) -> pd.DataFrame:
    """Add the metric columns to a table that holds summed day counts (pooled, never averaged)."""
    out = sums.copy()
    present = out.present_days.where(out.present_days > 0)
    out["attendance_rate"] = (out.present_days + 0.5 * out.half_days_unpaid) / out.scheduled_days
    out["late_rate"] = out.late_arrivals / present
    out["paid_leave_share"] = out.paid_leave_days / out.scheduled_days
    out["unpaid_absence_share"] = (out.unpaid_absence_days + 0.5 * out.half_days_unpaid) / out.scheduled_days
    out["wfh_share"] = out.wfh_days / present
    return out


def suppress_small(table: pd.DataFrame, min_group: int = MIN_GROUP) -> pd.DataFrame:
    """Blank the metric columns where fewer than `min_group` employees stand behind the row."""
    out = table.copy()
    small = ~(out["employees"] >= min_group)
    out.loc[small, METRIC_COLS] = float("nan")
    return out


def summarise(att: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Sum the day counts per group and add the metrics (no suppression)."""
    sums = att.groupby(by, as_index=False).agg(
        employees=("employee_id", "nunique"), **{c: (c, "sum") for c in SUM_COLS})
    return add_metrics(sums)


def company_monthly(att: pd.DataFrame) -> pd.DataFrame:
    return summarise(att, ["period_end_date"])


def department_monthly(att: pd.DataFrame) -> pd.DataFrame:
    return suppress_small(summarise(att, ["department_id", "period_end_date"]))


def rolling_3_month(att: pd.DataFrame) -> pd.DataFrame:
    """Pooled 3-month rate per department: sum of numerators over 3 months / sum of denominators.

    Needs all 3 months to exist, and at least MIN_GROUP employees in the latest of the three months."""
    months = pd.date_range(att.period_end_date.min(), att.period_end_date.max(), freq="ME")
    base = summarise(att, ["department_id", "period_end_date"])
    parts = []
    for dept, g in base.groupby("department_id"):
        g = g.set_index("period_end_date").reindex(months)
        roll = g[SUM_COLS].rolling(3, min_periods=3).sum()
        roll["employees"] = g["employees"]
        roll["department_id"] = dept
        parts.append(roll.rename_axis("period_end_date").reset_index())
    return suppress_small(add_metrics(pd.concat(parts, ignore_index=True)))


# ---- checks: each returns a list of problem strings (empty list = passed) ----

def check_row_reconciliation(att: pd.DataFrame) -> list[str]:
    total = att.present_days + att.paid_leave_days + att.unpaid_absence_days + att.half_days_unpaid
    bad = att[total != att.scheduled_days]
    return [f"{r.attendance_fact_id}: parts add to {t}, scheduled {r.scheduled_days}"
            for (_, r), t in zip(bad.head(10).iterrows(), total[bad.index].head(10))]


def check_stored_rate(att: pd.DataFrame) -> list[str]:
    formula = (att.present_days + 0.5 * att.half_days_unpaid) / att.scheduled_days
    bad = att[(formula - att.attendance_rate).abs() > RATE_TOLERANCE]
    return [f"{r.attendance_fact_id}: stored {r.attendance_rate:.4f}" for _, r in bad.head(10).iterrows()]


def check_bounds(att: pd.DataFrame) -> list[str]:
    problems = [f"{r.attendance_fact_id}: present {r.present_days} > scheduled {r.scheduled_days}"
                for _, r in att[att.present_days > att.scheduled_days].head(10).iterrows()]
    problems += [f"{r.attendance_fact_id}: wfh {r.wfh_days} > present {r.present_days}"
                 for _, r in att[att.wfh_days > att.present_days].head(10).iterrows()]
    return problems


def check_calendar(att: pd.DataFrame, calendar: pd.DataFrame) -> list[str]:
    """The largest scheduled_days in a month must equal the number of working days in dim_date."""
    working = calendar[calendar.is_working_day == "Y"].groupby("year_month").size()
    seen = att.groupby(att.period_end_date.dt.strftime("%Y-%m")).scheduled_days.max()
    return [f"{ym}: max scheduled {n}, calendar working days {working.get(ym)}"
            for ym, n in seen.items() if working.get(ym) != n]


def check_shares_sum_to_one(att: pd.DataFrame) -> list[str]:
    """Attendance rate + paid leave share + unpaid absence share must equal 1 for the whole company."""
    t = add_metrics(att[SUM_COLS].sum().to_frame().T)
    total = float((t.attendance_rate + t.paid_leave_share + t.unpaid_absence_share).iloc[0])
    return [] if abs(total - 1) < 1e-9 else [f"shares add to {total:.6f}"]


def check_company_rate_alternative(att: pd.DataFrame) -> list[str]:
    """Second route: weight the stored per-row rate by scheduled days. It must match the pooled sums."""
    pooled = company_monthly(att).set_index("period_end_date").attendance_rate
    alt = att.assign(w=att.attendance_rate * att.scheduled_days).groupby("period_end_date").agg(
        w=("w", "sum"), s=("scheduled_days", "sum"))
    alt = alt.w / alt.s
    bad = (pooled - alt).abs() > 0.0005
    return [f"{d:%Y-%m}: pooled {pooled[d]:.4f}, weighted {alt[d]:.4f}" for d in pooled[bad].index]


def missing_rows(att: pd.DataFrame, employee: pd.DataFrame) -> pd.DataFrame:
    """People employed on any day of a month with no attendance row for that month (reported, not imputed)."""
    p = employee.groupby("employee_id").agg(hire=("hire_date", "min"), exit=("exit_date", "max"))
    rows = []
    for me in sorted(att.period_end_date.unique()):
        me = pd.Timestamp(me)
        ms = me.replace(day=1)
        expected = set(p[(p.hire <= me) & (p["exit"].isna() | (p["exit"] >= ms))].index)
        have = set(att[att.period_end_date == me].employee_id)
        rows += [(e, me.date()) for e in sorted(expected - have)]
    return pd.DataFrame(rows, columns=["employee_id", "month_end_date"])


def main() -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    try:
        clean = Path(os.environ.get("DATA_DIR", "data")) / "clean"
        for name in ("attendance", "employee", "date"):
            if not (clean / f"{name}.parquet").exists():
                raise ConfigError(f"Not found: {clean / (name + '.parquet')}")
        att_all = pd.read_parquet(clean / "attendance.parquet")
        employee = pd.read_parquet(clean / "employee.parquet")
        calendar = pd.read_parquet(clean / "date.parquet")
    except PulseIQError as exc:
        log.error("STATUS=FAILED_CONFIG: %s", exc)
        return 2
    except Exception:
        log.exception("STATUS=FAILED_UNEXPECTED")
        return 3

    att, after_exit = split_after_exit(att_all, employee)
    log.info("Rows: %d total, %d used, %d excluded (attendance after exit)", len(att_all), len(att), len(after_exit))
    for _, r in after_exit.iterrows():
        log.info("  excluded %s %s month %s", r.attendance_fact_id, r.employee_id, r.period_end_date.date())
    missing = missing_rows(att, employee)
    log.info("Employed but no attendance row: %d %s", len(missing),
             [f"{r.employee_id} {r.month_end_date}" for r in missing.itertuples()])

    monthly = company_monthly(att)
    show = monthly.assign(month=monthly.period_end_date.dt.strftime("%Y-%m"))[
        ["month", "employees", "attendance_rate", "late_rate", "paid_leave_share", "unpaid_absence_share", "wfh_share"]]
    print("\nCompany by month (pooled):")
    print(show.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    print()

    checks = {
        "A1 rows reconcile: present + paid + unpaid + half = scheduled": check_row_reconciliation(att),
        "A2 stored attendance_rate equals the M13 formula": check_stored_rate(att),
        "A3 present <= scheduled and wfh <= present": check_bounds(att),
        "A4 scheduled days equal calendar working days": check_calendar(att, calendar),
        "A5 rate + paid leave share + unpaid share = 1": check_shares_sum_to_one(att),
        "A6 pooled monthly rate equals weighted stored rate": check_company_rate_alternative(att),
    }
    failed = 0
    for label, problems in checks.items():
        if problems:
            failed += 1
            log.error("MISMATCH  %s\n  %s", label, "\n  ".join(problems))
        else:
            log.info("MATCH     %s", label)
    log.info("STATUS=%s", "ALL_MATCH" if not failed else f"{failed}_CHECK(S)_FAILED")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
