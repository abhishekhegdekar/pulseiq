"""Helper columns (year, month, tenure), added to rows that passed validation.

Tenure is measured to the exit date, or to the fixed DEMO_TODAY for people still
employed. It never uses today's date, so the same input always gives the same output.
"""
import pandas as pd


def add_helper_columns(name: str, df: pd.DataFrame, reporting_date) -> pd.DataFrame:
    out = df.copy()
    cutoff = pd.Timestamp(reporting_date)
    if name == "employee":
        end = out["exit_date"].fillna(cutoff).clip(upper=cutoff)
        out["hire_year"] = out["hire_date"].dt.year
        out["hire_month"] = out["hire_date"].dt.month
        out["tenure_days"] = (end - out["hire_date"]).dt.days
        out["tenure_years"] = (out["tenure_days"] / 365.25).round(2)
    elif name in ("payroll", "attendance"):
        out["period_year"] = out["period_end_date"].dt.year
        out["period_month"] = out["period_end_date"].dt.month
    elif name == "leave":
        out["start_year"] = out["start_date"].dt.year
        out["start_month"] = out["start_date"].dt.month
    return out
