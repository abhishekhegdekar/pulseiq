"""Transform step: standardise text, dates, numbers and drop exact duplicates.

This step never changes business values and never fills missing values.
Values that cannot be converted to their type become missing (NaN/NaT) AND are
recorded in the `_issues` column, so validation can reject those rows with a
reason instead of the problem being hidden.
"""
import logging

import pandas as pd

log = logging.getLogger("pulseiq.transform")

DATE_COLS: dict[str, list[str]] = {
    "department": [],
    "role": [],
    "leave_type": [],
    "date": ["date", "month_start_date", "month_end_date"],
    "employee": ["date_of_birth", "hire_date", "exit_date", "valid_from", "valid_to"],
    "payroll": ["period_end_date"],
    "attendance": ["period_end_date"],
    "leave": ["start_date", "end_date", "applied_on", "decided_on"],
}

NUMERIC_COLS: dict[str, list[str]] = {
    "department": [],
    "role": ["level", "band_min_annual", "band_mid_annual", "band_max_annual", "band_reference_year"],
    "leave_type": ["annual_quota_days", "max_carry_forward_days"],
    "date": ["date_key", "year", "quarter", "month_number", "week_of_year", "fiscal_month_number"],
    "employee": ["employee_key", "job_level"],
    "payroll": [
        "employee_key", "date_key", "payable_days", "lop_days", "overtime_hours_paid",
        "monthly_fixed_gross", "basic", "hra", "conveyance", "medical",
        "special_allowance", "earned_fixed_pay", "overtime_pay", "variable_pay",
        "gross_pay", "pf_employee", "esi_employee", "professional_tax", "tds",
        "other_deductions", "total_deductions", "net_pay", "pf_employer",
        "esi_employer", "employer_cost", "headcount_flag",
    ],
    "attendance": [
        "date_key", "employee_key", "scheduled_days", "present_days", "wfh_days",
        "half_days_unpaid", "paid_leave_days", "unpaid_absence_days",
        "late_arrivals", "avg_hours_worked", "overtime_hours", "attendance_rate",
    ],
    "leave": ["employee_key", "start_date_key", "end_date_key", "days"],
}

# Columns that are only row labels. Two rows that differ ONLY in these are the same record.
DEDUPE_IGNORE: dict[str, list[str]] = {
    "department": [],
    "role": [],
    "leave_type": [],
    "date": [],
    "employee": [],
    "payroll": ["payroll_item_id"],
    "attendance": ["attendance_fact_id"],
    "leave": [],
}

COLLAPSE_SPACES_COLS = {"full_name"}
HELPER_COLS = ("source_row", "_issues")


def _flag(issues: pd.Series, mask: pd.Series, text: str) -> None:
    """Append `text` to the issue string of every row where mask is True."""
    issues.loc[mask] = issues.loc[mask].map(lambda s: f"{s}; {text}" if s else text)


def transform(name: str, df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    out = df.copy()
    out["source_row"] = out.index + 2  # row number in the Excel sheet (row 1 is the header)
    issues = pd.Series("", index=out.index, dtype="object")
    stats = {"rows_in": len(df), "text_cells_changed": 0, "conversion_issues": 0}

    # 1. Text: trim, collapse spaces in names, blank -> missing. Spelling and case are kept.
    for col in df.columns:
        if not pd.api.types.is_string_dtype(out[col]):  # inspects the values, not just the dtype label
            continue
        before = out[col]
        cleaned = before.str.strip()
        if col in COLLAPSE_SPACES_COLS:
            cleaned = cleaned.str.replace(r"\s+", " ", regex=True)
        cleaned = cleaned.mask(cleaned == "", pd.NA)
        changed = before.notna() & ~((before == cleaned) | (before.isna() & cleaned.isna()))
        stats["text_cells_changed"] += int(changed.sum())
        out[col] = cleaned

    # 2. Dates and numbers: convert; failures become missing and are recorded.
    for col in DATE_COLS[name]:
        parsed = pd.to_datetime(out[col], format="ISO8601", errors="coerce")  # strict: no day/month guessing
        bad = out[col].notna() & parsed.isna()
        _flag(issues, bad, f"unparseable date in {col}")
        out[col] = parsed
    for col in NUMERIC_COLS[name]:
        parsed = pd.to_numeric(out[col], errors="coerce")
        bad = out[col].notna() & parsed.isna()
        _flag(issues, bad, f"non-numeric value in {col}")
        out[col] = parsed
    out["_issues"] = issues
    stats["conversion_issues"] = int((issues != "").sum())

    # 3. Exact duplicates (all columns equal except row labels): keep the first, drop the rest.
    compare = [c for c in df.columns if c not in DEDUPE_IGNORE[name]]
    dup = out.duplicated(subset=compare, keep="first")
    stats["duplicates_removed"] = int(dup.sum())
    if dup.any():
        log.warning("%s: removed %d exact duplicate row(s); sheet rows: %s",
                    name, dup.sum(), out.loc[dup, "source_row"].tolist()[:20])
    out = out.loc[~dup]
    stats["rows_after_dedupe"] = len(out)

    log.info("Transformed %-10s %s", name, stats)
    return out, stats
