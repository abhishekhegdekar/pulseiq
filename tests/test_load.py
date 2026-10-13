"""Loader tests that need no database: row conversion and load order."""
import datetime as dt

import pandas as pd

from pulseiq.load import LOAD_ORDER, rows_from_frame


def test_rows_from_frame_converts_missing_values_and_dates():
    df = pd.DataFrame({
        "id": ["a", "b"],
        "when": pd.to_datetime(["2026-01-31", None]),
        "amount": [1.5, float("nan")],
        "n": [1, 2],
    })
    rows = rows_from_frame(df, ["id", "when", "amount", "n"])
    assert rows[0] == ("a", dt.date(2026, 1, 31), 1.5, 1)
    assert rows[1] == ("b", None, None, 2)
    assert type(rows[0][3]) is int          # plain Python int, not numpy


def test_rows_from_frame_follows_the_requested_column_order():
    df = pd.DataFrame({"x": [1], "y": [2]})
    assert rows_from_frame(df, ["y", "x"]) == [(2, 1)]


def test_parents_load_before_children():
    order = [table for _, table, _ in LOAD_ORDER]
    for parent, child in [("dim_department", "dim_role"), ("dim_role", "dim_employee"),
                          ("dim_employee", "fact_payroll"), ("dim_date", "fact_attendance"),
                          ("dim_leave_type", "fact_leave"), ("dim_employee", "fact_leave")]:
        assert order.index(parent) < order.index(child)


def test_every_clean_dataset_is_loaded_once():
    assert sorted(n for n, _, _ in LOAD_ORDER) == sorted(
        ["department", "leave_type", "date", "role", "employee", "payroll", "attendance", "leave"])
