"""Extract step: read the source sheets and check their structure.

Structural problems (missing file, sheet or column) raise StructuralError.
Bad *values* are not handled here; that is the job of validation.
"""
import logging
from pathlib import Path

import pandas as pd

from pulseiq.errors import StructuralError

log = logging.getLogger("pulseiq.extract")

# dataset name -> (sheet name in the workbook, columns we require)
SOURCES: dict[str, tuple[str, list[str]]] = {
    "employee": ("dim_employee", [
        "employee_key", "employee_id", "full_name", "gender", "date_of_birth",
        "hire_date", "exit_date", "employment_status", "employment_type",
        "department_id", "role_id", "role_title", "job_level", "manager_id",
        "work_location", "work_mode", "highest_education", "valid_from",
        "valid_to", "is_current", "change_reason",
    ]),
    "payroll": ("fact_payroll", [
        "payroll_item_id", "run_id", "employee_id", "date_key", "employee_key",
        "period_end_date", "department_id", "role_id", "payable_days", "lop_days",
        "overtime_hours_paid", "variable_pay_type", "monthly_fixed_gross", "basic",
        "hra", "conveyance", "medical", "special_allowance", "earned_fixed_pay",
        "overtime_pay", "variable_pay", "gross_pay", "pf_employee", "esi_employee",
        "professional_tax", "tds", "other_deductions", "total_deductions",
        "net_pay", "pf_employer", "esi_employer", "employer_cost", "headcount_flag",
    ]),
    "attendance": ("fact_attendance_monthly", [
        "attendance_fact_id", "employee_id", "date_key", "employee_key",
        "department_id", "scheduled_days", "present_days", "wfh_days",
        "half_days_unpaid", "paid_leave_days", "unpaid_absence_days",
        "late_arrivals", "avg_hours_worked", "overtime_hours", "attendance_rate",
        "period_end_date",
    ]),
    "leave": ("fact_leave", [
        "leave_request_id", "employee_id", "employee_key", "leave_type_code",
        "start_date_key", "end_date_key", "start_date", "end_date", "days",
        "status", "applied_on", "decided_on", "approver_id", "reason",
    ]),
}


def extract(workbook: Path) -> dict[str, pd.DataFrame]:
    """Read every source sheet, log its row count, and return the raw frames."""
    if not workbook.is_file():
        raise StructuralError(f"Input workbook not found: {workbook}")

    try:
        xl = pd.ExcelFile(workbook)
    except Exception as exc:  # unreadable or not a real xlsx
        raise StructuralError(f"Cannot open workbook {workbook}: {exc}") from exc

    frames: dict[str, pd.DataFrame] = {}
    with xl:
        for name, (sheet, required) in SOURCES.items():
            if sheet not in xl.sheet_names:
                raise StructuralError(f"Sheet '{sheet}' (dataset '{name}') is missing from {workbook.name}")
            df = xl.parse(sheet)
            missing = [c for c in required if c not in df.columns]
            if missing:
                raise StructuralError(f"Sheet '{sheet}' is missing required columns: {missing}")
            extra = [c for c in df.columns if c not in required]
            if extra:
                log.warning("Sheet '%s' has unexpected extra columns (kept): %s", sheet, extra)
            log.info("Extracted %-10s from sheet %-24s rows_in=%d", name, sheet, len(df))
            frames[name] = df
    return frames
