"""Validation step: split each dataset into valid rows and rejected rows with reasons.

Two kinds of problem are kept apart:
  * Row problems (bad values)      -> the row goes to the rejected set with a reason.
  * Structural problems (wrong columns/types for a whole column) -> StructuralError.

Reject reasons name the column and the rule, never the value, so salary figures
do not leak into logs.
"""
import logging
from datetime import date

import pandas as pd
import pandera.pandas as pa
from pandera.errors import SchemaErrors

from pulseiq.errors import PulseIQError, StructuralError

log = logging.getLogger("pulseiq.validate")

PAYROLL_NONNEGATIVE = [
    "payable_days", "lop_days", "overtime_hours_paid", "monthly_fixed_gross", "basic",
    "hra", "conveyance", "medical", "special_allowance", "earned_fixed_pay",
    "overtime_pay", "variable_pay", "gross_pay", "pf_employee", "esi_employee",
    "professional_tax", "tds", "other_deductions", "total_deductions", "net_pay",
    "pf_employer", "esi_employer", "employer_cost",
]
ATTENDANCE_NONNEGATIVE = [
    "scheduled_days", "present_days", "wfh_days", "half_days_unpaid", "paid_leave_days",
    "unpaid_absence_days", "late_arrivals", "avg_hours_worked", "overtime_hours",
]


ROW_LEVEL_CHECKS = {
    "hire_date_after_exit_date", "valid_from_after_valid_to",
    "duplicate_current_employee_id", "end_date_before_start_date",
}


def _nonneg() -> pa.Column:
    return pa.Column(checks=pa.Check.ge(0), nullable=False)


def _required() -> pa.Column:
    return pa.Column(nullable=False)


def build_schemas(reporting_date: date) -> dict[str, pa.DataFrameSchema]:
    cutoff = pd.Timestamp(reporting_date)

    employee = pa.DataFrameSchema(
        columns={
            "employee_key": pa.Column(nullable=False, unique=True),
            "employee_id": _required(),
            "full_name": _required(),
            "date_of_birth": pa.Column(pa.DateTime, nullable=False),
            "hire_date": pa.Column(pa.DateTime, pa.Check.le(cutoff), nullable=False),
            "exit_date": pa.Column(pa.DateTime, nullable=True),  # empty = still employed
            "valid_from": pa.Column(pa.DateTime, nullable=False),
            "valid_to": pa.Column(pa.DateTime, nullable=False),
            "is_current": pa.Column(checks=pa.Check.isin(["Y", "N"]), nullable=False),
            "department_id": _required(),
            "role_id": _required(),
        },
        checks=[
            pa.Check(lambda df: df["exit_date"].isna() | (df["hire_date"] <= df["exit_date"]),
                     name="hire_date_after_exit_date"),
            pa.Check(lambda df: df["valid_from"] <= df["valid_to"],
                     name="valid_from_after_valid_to"),
            pa.Check(_unique_current_employee_id, name="duplicate_current_employee_id"),
        ],
    )

    payroll = pa.DataFrameSchema(
        columns={
            "payroll_item_id": pa.Column(nullable=False, unique=True),
            "run_id": _required(),
            "employee_key": _required(),
            "period_end_date": pa.Column(pa.DateTime, pa.Check.le(cutoff), nullable=False),
            "variable_pay_type": pa.Column(nullable=True),  # empty = no variable pay
            **{c: _nonneg() for c in PAYROLL_NONNEGATIVE},
        },
        unique=["employee_key", "run_id"],
    )

    attendance = pa.DataFrameSchema(
        columns={
            "attendance_fact_id": pa.Column(nullable=False, unique=True),
            "employee_key": _required(),
            "date_key": _required(),
            "period_end_date": pa.Column(pa.DateTime, pa.Check.le(cutoff), nullable=False),
            "attendance_rate": pa.Column(checks=pa.Check.in_range(0, 1), nullable=False),
            **{c: _nonneg() for c in ATTENDANCE_NONNEGATIVE},
        },
        unique=["employee_key", "date_key"],
    )

    leave = pa.DataFrameSchema(
        columns={
            "leave_request_id": pa.Column(nullable=False, unique=True),
            "employee_key": _required(),
            "start_date": pa.Column(pa.DateTime, nullable=False),
            "end_date": pa.Column(pa.DateTime, nullable=False),
            "applied_on": pa.Column(pa.DateTime, nullable=False),
            "decided_on": pa.Column(pa.DateTime, nullable=True),  # empty while Pending
            "days": pa.Column(checks=pa.Check.gt(0), nullable=False),
        },
        checks=[pa.Check(lambda df: df["end_date"] >= df["start_date"],
                         name="end_date_before_start_date")],
    )
    return {"employee": employee, "payroll": payroll, "attendance": attendance, "leave": leave}


def _unique_current_employee_id(df: pd.DataFrame) -> pd.Series:
    """True for rows that are fine; False where a current employee_id appears twice."""
    current = df["is_current"].eq("Y")
    dup = df.loc[current, "employee_id"].duplicated(keep=False)
    return ~dup.reindex(df.index, fill_value=False)


def _schema_reasons(schema: pa.DataFrameSchema, df: pd.DataFrame, name: str) -> pd.Series:
    reasons = pd.Series("", index=df.index, dtype="object")
    try:
        schema.validate(df, lazy=True)
    except SchemaErrors as err:
        cases = err.failure_cases
        structural = cases[cases["index"].isna()]
        if not structural.empty:
            detail = structural[["column", "check"]].drop_duplicates().to_dict("records")
            raise StructuralError(f"Dataset '{name}' has a column-level problem: {detail}") from err
        for idx, group in cases.groupby("index"):
            parts = set()
            for column, check in zip(group["column"], group["check"]):
                if check in ROW_LEVEL_CHECKS:  # reported once per column by pandera; name the rule only
                    parts.add(check)
                elif check.startswith("multiple_fields_uniqueness"):
                    keys = sorted(group.loc[group["check"] == check, "column"].dropna().unique())
                    parts.add(f"duplicate key ({', '.join(keys)})")
                else:
                    parts.add(f"{column}: {check}")
            reasons.loc[idx] = "; ".join(sorted(parts))
    return reasons


def validate(name: str, df: pd.DataFrame, transform_stats: dict, schema: pa.DataFrameSchema,
             valid_employee_keys: set | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Return (clean rows, rejected rows, stats) for one dataset."""
    reasons = _schema_reasons(schema, df, name)

    if valid_employee_keys is not None:  # facts must point at a valid employee
        orphan = ~df["employee_key"].isin(valid_employee_keys)
        reasons = reasons.where(~orphan, reasons.map(
            lambda s: f"{s}; employee_key: not found among valid employees" if s
            else "employee_key: not found among valid employees"))

    all_reasons = pd.Series(
        [("; ".join(x for x in (a, b) if x)) for a, b in zip(df["_issues"], reasons)],
        index=df.index, dtype="object")
    bad = all_reasons != ""

    helper = ["_issues"]
    clean = df.loc[~bad].drop(columns=helper + ["source_row"])
    rejected = df.loc[bad].drop(columns=helper).assign(reject_reason=all_reasons[bad], dataset=name)
    rejected = rejected[["dataset", "source_row", "reject_reason"]
                        + [c for c in rejected.columns if c not in ("dataset", "source_row", "reject_reason")]]

    stats = {
        "rows_in": transform_stats["rows_in"],
        "duplicates_removed": transform_stats["duplicates_removed"],
        "rows_rejected": len(rejected),
        "rows_out": len(clean),
    }
    if stats["rows_in"] != stats["rows_out"] + stats["rows_rejected"] + stats["duplicates_removed"]:
        raise PulseIQError(f"Row reconciliation failed for {name}: {stats}")
    log.info("Validated %-10s %s", name, stats)
    return clean, rejected, stats
