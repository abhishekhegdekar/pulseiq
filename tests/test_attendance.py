"""Tests for pulseiq.attendance (no database, small made-up data)."""
import pandas as pd
import pytest

from pulseiq.attendance import (MIN_GROUP, add_metrics, check_bounds, check_calendar, check_company_rate_alternative,
                                check_row_reconciliation, check_shares_sum_to_one, check_stored_rate,
                                company_monthly, department_monthly, missing_rows, rolling_3_month,
                                split_after_exit)

T = pd.Timestamp


def _row(fid, emp, month_end, dept="D01", sched=20, present=18, wfh=5, half=0, paid=2, unpaid=0, late=1):
    rate = (present + 0.5 * half) / sched
    return dict(attendance_fact_id=fid, employee_id=emp, department_id=dept, period_end_date=T(month_end),
                scheduled_days=sched, present_days=present, wfh_days=wfh, half_days_unpaid=half,
                paid_leave_days=paid, unpaid_absence_days=unpaid, late_arrivals=late, attendance_rate=rate)


def test_rate_is_pooled_not_averaged():
    # A: 20 of 20 present; B: 1 of 2 scheduled. Pooled = 21/22, average of rates would be 0.75.
    df = pd.DataFrame([_row("1", "E1", "2026-01-31", sched=20, present=20, paid=0),
                       _row("2", "E2", "2026-01-31", sched=2, present=1, paid=1)])
    got = company_monthly(df).attendance_rate.iloc[0]
    assert got == pytest.approx(21 / 22)


def test_half_day_counts_half_and_shares_add_to_one():
    df = pd.DataFrame([_row("1", "E1", "2026-01-31", sched=20, present=17, half=2, paid=1, unpaid=0)])
    m = company_monthly(df).iloc[0]
    assert m.attendance_rate == pytest.approx((17 + 1) / 20)
    assert m.unpaid_absence_share == pytest.approx(1 / 20)
    assert m.attendance_rate + m.paid_leave_share + m.unpaid_absence_share == pytest.approx(1)
    assert check_shares_sum_to_one(df) == []


def test_late_rate_blank_when_nobody_present():
    t = add_metrics(pd.DataFrame([dict(scheduled_days=20, present_days=0, wfh_days=0, half_days_unpaid=0,
                                       paid_leave_days=0, unpaid_absence_days=20, late_arrivals=0)]))
    assert pd.isna(t.late_rate.iloc[0]) and t.attendance_rate.iloc[0] == 0


def test_small_departments_are_blank_not_zero():
    big = [_row(f"b{i}", f"B{i}", "2026-01-31", dept="D01") for i in range(MIN_GROUP)]
    small = [_row(f"s{i}", f"S{i}", "2026-01-31", dept="D00") for i in range(MIN_GROUP - 1)]
    out = department_monthly(pd.DataFrame(big + small)).set_index("department_id")
    assert out.loc["D01", "attendance_rate"] == pytest.approx(0.9)
    assert pd.isna(out.loc["D00", "attendance_rate"])


def test_rolling_needs_three_months_and_pools_sums():
    rows = []
    for m, present in (("2026-01-31", 20), ("2026-02-28", 10), ("2026-03-31", 20)):
        rows += [_row(f"{m}{i}", f"E{i}", m, sched=20, present=present, paid=20 - present) for i in range(MIN_GROUP)]
    out = rolling_3_month(pd.DataFrame(rows)).set_index("period_end_date")
    assert pd.isna(out.loc[T("2026-02-28"), "attendance_rate"])
    assert out.loc[T("2026-03-31"), "attendance_rate"] == pytest.approx(50 / 60)


def test_rolling_blank_across_a_missing_month():
    rows = []
    for m in ("2026-01-31", "2026-03-31", "2026-04-30"):   # February absent
        rows += [_row(f"{m}{i}", f"E{i}", m) for i in range(MIN_GROUP)]
    out = rolling_3_month(pd.DataFrame(rows)).set_index("period_end_date")
    assert pd.isna(out.loc[T("2026-03-31"), "attendance_rate"])
    assert pd.isna(out.loc[T("2026-04-30"), "attendance_rate"])


def test_rows_after_exit_are_split_out():
    employee = pd.DataFrame({"employee_id": ["E1", "E2"], "exit_date": [T("2026-01-15"), pd.NaT]})
    att = pd.DataFrame([_row("1", "E1", "2026-01-31"), _row("2", "E1", "2026-02-28"), _row("3", "E2", "2026-02-28")])
    kept, dropped = split_after_exit(att, employee)
    assert list(kept.attendance_fact_id) == ["1", "3"] and list(dropped.attendance_fact_id) == ["2"]


def test_missing_rows_lists_employed_people_without_a_row():
    employee = pd.DataFrame({"employee_id": ["E1", "E2"], "hire_date": [T("2025-01-01"), T("2025-01-01")],
                             "exit_date": [pd.NaT, pd.NaT]})
    att = pd.DataFrame([_row("1", "E1", "2026-01-31"), _row("2", "E2", "2026-01-31"), _row("3", "E1", "2026-02-28")])
    miss = missing_rows(att, employee)
    assert list(miss.employee_id) == ["E2"] and str(miss.month_end_date.iloc[0]) == "2026-02-28"


def test_checks_catch_bad_rows():
    good = pd.DataFrame([_row("1", "E1", "2026-01-31")])
    assert check_row_reconciliation(good) == [] and check_stored_rate(good) == [] and check_bounds(good) == []
    bad = good.assign(paid_leave_days=5, attendance_rate=0.5, wfh_days=99)
    assert check_row_reconciliation(bad) and check_stored_rate(bad) and check_bounds(bad)


def test_calendar_check_compares_with_working_days():
    calendar = pd.DataFrame({"year_month": ["2026-01"] * 3, "is_working_day": ["Y", "Y", "N"]})
    assert check_calendar(pd.DataFrame([_row("1", "E1", "2026-01-31", sched=2, present=2, paid=0)]), calendar) == []
    assert check_calendar(pd.DataFrame([_row("1", "E1", "2026-01-31", sched=3, present=3, paid=0)]), calendar)


def test_alternative_route_agrees_with_pooled_rate():
    df = pd.DataFrame([_row("1", "E1", "2026-01-31"), _row("2", "E2", "2026-01-31", present=15, paid=5)])
    assert check_company_rate_alternative(df) == []
