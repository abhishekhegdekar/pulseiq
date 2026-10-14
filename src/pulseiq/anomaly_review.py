"""Review list from the AI/ML attendance anomaly flags (workbook sheet fact_anomaly).

The flags are NOT used in any metric. This only checks them against our attendance facts and lists
the ones our monthly data contradicts. Join key: employee_id + month (record_id never matches attendance_fact_id).
Run: docker compose run --rm --build load python -m pulseiq.anomaly_review
"""
from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path

import pandas as pd

log = logging.getLogger("pulseiq.anomaly_review")
SOURCE = "attendance_monthly_features"


def load_flags(workbook: Path) -> pd.DataFrame:
    a = pd.read_excel(workbook, sheet_name="fact_anomaly")
    a = a[a.source_dataset == SOURCE].copy()
    a["month"] = pd.to_datetime(a.period) + pd.offsets.MonthEnd(0)
    return a


def join_flags(flags: pd.DataFrame, att: pd.DataFrame) -> pd.DataFrame:
    return flags.merge(att, left_on=["employee_id", "month"], right_on=["employee_id", "period_end_date"], how="left")


def claimed_days(text: str) -> int | None:
    m = re.match(r"\s*(\d+) consecutive unpaid absence days", str(text))
    return int(m.group(1)) if m else None


def supported(row: pd.Series) -> bool | None:
    """True/False when monthly data can confirm the reason, None when it cannot be checked."""
    if pd.isna(row.present_days):
        return False
    if row.reason_code == "NO_ATTENDANCE":
        return bool(row.present_days == 0)
    if row.reason_code == "LONG_UNPAID_ABSENCE":
        n = claimed_days(row.reason_text)
        return None if n is None else bool(row.unpaid_absence_days >= n)
    return None


def summary(j: pd.DataFrame) -> pd.DataFrame:
    j = j.assign(check=j.apply(supported, axis=1))
    g = j.groupby("reason_code")
    return pd.DataFrame({
        "flags": g.size(),
        "matched_to_attendance": g.apply(lambda d: int(d.attendance_fact_id.notna().sum()), include_groups=False),
        "supported": g.apply(lambda d: int((d.check == True).sum()), include_groups=False),
        "contradicted": g.apply(lambda d: int((d.check == False).sum()), include_groups=False),
        "not_checkable": g.apply(lambda d: int(d.check.isna().sum()), include_groups=False),
    }).reset_index()


def zero_present_coverage(att: pd.DataFrame, flags: pd.DataFrame) -> tuple[int, int]:
    z = att[att.present_days == 0]
    keys = set(zip(flags[flags.reason_code == "NO_ATTENDANCE"].employee_id, flags[flags.reason_code == "NO_ATTENDANCE"].month))
    return len(z), sum((e, m) in keys for e, m in zip(z.employee_id, z.period_end_date))


def main() -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(levelname)-7s %(message)s")
    workbook = Path(os.environ.get("INPUT_WORKBOOK", ""))
    clean = Path(os.environ.get("DATA_DIR", "data")) / "clean"
    if not workbook.exists() or not (clean / "attendance.parquet").exists():
        log.error("STATUS=FAILED_CONFIG: workbook or clean attendance not found")
        return 2
    att = pd.read_parquet(clean / "attendance.parquet")
    flags = load_flags(workbook)
    j = join_flags(flags, att)
    log.info("Attendance flags: %d (of all flags in the sheet); unmatched to attendance: %d",
             len(flags), int(j.attendance_fact_id.isna().sum()))
    print("\nFlags checked against our attendance facts:")
    print(summary(j).to_string(index=False))
    z, covered = zero_present_coverage(att, flags)
    print(f"\nRows with zero present days: {z}; of these flagged NO_ATTENDANCE: {covered}")
    j["check"] = j.apply(supported, axis=1)
    bad = j[j.check == False]  # noqa: E712
    print(f"\nReview list: {len(bad)} flags our monthly data contradicts (first 10 shown)")
    print(bad[["employee_id", "month", "reason_code", "anomaly_score", "present_days", "scheduled_days", "unpaid_absence_days"]]
          .head(10).to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
