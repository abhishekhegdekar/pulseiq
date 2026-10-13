"""Validation step: split each dataset into valid rows and rejected rows with reasons.

Two kinds of problem are kept apart:
  * Row problems (bad values)      -> the row goes to the rejected set with a reason.
  * Structural problems (wrong columns/types for a whole column) -> StructuralError.

Reject reasons name the column and the rule, never the value, so salary figures
do not leak into logs.

Rows can also be rejected because they point at something that is not valid:
an unknown (or itself rejected) department, role, date, leave type or employee,
or a department/role that disagrees with the employee version they point at.
"""
import logging
from collections.abc import Sequence
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

# Whole-row checks: pandera reports them once per column, so we name only the rule.
ROW_LEVEL_CHECKS = {
    "hire_date_after_exit_date", "valid_from_after_valid_to",
    "duplicate_current_employee_id", "end_date_before_start_date",
    "pay_band_out_of_order", "date_key_does_not_match_date", "working_day_flag_inconsistent",
}

# A reference says: values of `column` must be found in `valid_values` (a set taken from
# the VALID rows of another dataset). `label` only appears in the reject reason.
Reference = tuple[str, set, str]


def _nonneg() -> pa.Column:
    return pa.Column(checks=pa.Check.ge(0), nullable=False)


def _required() -> pa.Column:
    return pa.Column(nullable=False)


def _yes_no(nullable: bool = False) -> pa.Column:
    return pa.Column(checks=pa.Check.isin(["Y", "N"]), nullable=nullable)


def _unique_current_employee_id(df: pd.DataFrame) -> pd.Series:
    """True for rows that are fine; False where a current employee_id appears twice."""
    current = df["is_current"].eq("Y")
    dup = df.loc[current, "employee_id"].duplicated(keep=False)
    return ~dup.reindex(df.index, fill_value=False)


def _working_day_consistent(df: pd.DataFrame) -> pd.Series:
    expected = (df["is_weekend"].eq("N") & df["is_holiday"].eq("N")).map({True: "Y", False: "N"})
    return df["is_working_day"].eq(expected)


def build_schemas(reporting_date: date) -> dict[str, pa.DataFrameSchema]:
    cutoff = pd.Timestamp(reporting_date)

    department = pa.DataFrameSchema(columns={
        "department_id": pa.Column(nullable=False, unique=True),
        "department_name": pa.Column(nullable=False, unique=True),
        "cost_center": pa.Column(nullable=False, unique=True),
        "is_leadership": _yes_no(),
    })

    role = pa.DataFrameSchema(
        columns={
            "role_id": pa.Column(nullable=False, unique=True),
            "department_id": _required(),
            "role_title": _required(),
            "level": pa.Column(checks=pa.Check.in_range(1, 7), nullable=False),
            "band_min_annual": pa.Column(checks=pa.Check.gt(0), nullable=False),
            "band_mid_annual": pa.Column(checks=pa.Check.gt(0), nullable=False),
            "band_max_annual": pa.Column(checks=pa.Check.gt(0), nullable=False),
            "overtime_eligible": _yes_no(),
        },
        checks=[pa.Check(lambda df: (df["band_min_annual"] <= df["band_mid_annual"])
                         & (df["band_mid_annual"] <= df["band_max_annual"]),
                         name="pay_band_out_of_order")],
    )

    leave_type = pa.DataFrameSchema(columns={
        "leave_type_code": pa.Column(nullable=False, unique=True),
        "leave_type_name": _required(),
        "pay_type": pa.Column(checks=pa.Check.isin(["Paid", "Unpaid"]), nullable=False),
        "annual_quota_days": _nonneg(),
        "max_carry_forward_days": _nonneg(),
    })

    calendar = pa.DataFrameSchema(
        columns={
            "date": pa.Column(pa.DateTime, nullable=False, unique=True),
            "date_key": pa.Column(nullable=False, unique=True),
            "is_weekend": _yes_no(),
            "is_holiday": _yes_no(),
            "is_working_day": _yes_no(),
            "is_month_end": _yes_no(),
        },
        checks=[
            pa.Check(lambda df: df["date_key"] == df["date"].dt.strftime("%Y%m%d").astype("int64"),
                     name="date_key_does_not_match_date"),
            pa.Check(_working_day_consistent, name="working_day_flag_inconsistent"),
        ],
    )

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
    return {"department": department, "role": role, "leave_type": leave_type, "date": calendar,
            "employee": employee, "payroll": payroll, "attendance": attendance, "leave": leave}


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


def _add(reasons: pd.Series, mask: pd.Series, text: str) -> None:
    """Append `text` to the reason of every row where mask is True."""
    reasons.loc[mask] = reasons.loc[mask].map(lambda s: f"{s}; {text}" if s else text)


def count_overlapping_versions(df: pd.DataFrame) -> int:
    """History versions of one employee whose validity window overlaps the next version's."""
    ordered = df.sort_values(["employee_id", "valid_from"])
    next_from = ordered.groupby("employee_id")["valid_from"].shift(-1)
    return int((next_from.notna() & (next_from <= ordered["valid_to"])).sum())


def validate(name: str, df: pd.DataFrame, transform_stats: dict, schema: pa.DataFrameSchema,
             references: Sequence[Reference] = (),
             employee_lookup: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Return (clean rows, rejected rows, stats) for one dataset.

    references:      (column, valid values, label): rows whose value is not in the set are rejected.
    employee_lookup: DataFrame indexed by employee_key with department_id / role_id; fact rows
                     must agree with the employee version they point at.
    """
    reasons = _schema_reasons(schema, df, name)

    for column, valid_values, label in references:
        _add(reasons, df[column].notna() & ~df[column].isin(valid_values),
             f"{column}: not found among valid {label}")

    if employee_lookup is not None:
        known = df["employee_key"].isin(employee_lookup.index)
        for column in ("department_id", "role_id"):
            if column in df.columns:
                expected = df["employee_key"].map(employee_lookup[column])
                _add(reasons, known & (df[column] != expected),
                     f"{column}: does not match the employee version")

    all_reasons = pd.Series(
        [("; ".join(x for x in (a, b) if x)) for a, b in zip(df["_issues"], reasons)],
        index=df.index, dtype="object")
    bad = all_reasons != ""

    clean = df.loc[~bad].drop(columns=["_issues", "source_row"])
    rejected = df.loc[bad].drop(columns=["_issues"]).assign(reject_reason=all_reasons[bad], dataset=name)
    rejected = rejected[["dataset", "source_row", "reject_reason"]
                        + [c for c in rejected.columns if c not in ("dataset", "source_row", "reject_reason")]]

    stats = {
        "rows_in": transform_stats["rows_in"],
        "duplicates_removed": transform_stats["duplicates_removed"],
        "rows_rejected": len(rejected),
        "rows_out": len(clean),
    }
    if name == "employee":  # a warning, not a rejection: the "latest valid_from" rule still picks one version
        overlaps = count_overlapping_versions(df)
        stats["warnings"] = {"overlapping_versions": overlaps}
        if overlaps:
            log.warning("employee: %d history version(s) overlap the next version's validity window", overlaps)
    if stats["rows_in"] != stats["rows_out"] + stats["rows_rejected"] + stats["duplicates_removed"]:
        raise PulseIQError(f"Row reconciliation failed for {name}: {stats}")
    log.info("Validated %-10s %s", name, stats)
    return clean, rejected, stats
