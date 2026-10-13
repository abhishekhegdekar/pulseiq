"""Tests for the independent (pandas) side of the SQL answer checks. No database needed."""
import pandas as pd

from pulseiq.check_answers import _same, expected_q1, expected_q2


def _emp(employee_id, dept, valid_from, hire="2020-01-01", exit_=None):
    return {"employee_id": employee_id, "department_id": dept, "valid_from": pd.Timestamp(valid_from),
            "hire_date": pd.Timestamp(hire), "exit_date": pd.Timestamp(exit_) if exit_ else pd.NaT}


def test_q1_uses_latest_version_and_excludes_leavers():
    employee = pd.DataFrame([
        _emp("E1", "D01", "2020-01-01"), _emp("E1", "D02", "2026-02-04"),          # transferred -> D02
        _emp("E2", "D01", "2020-01-01", exit_="2026-09-30"),                         # leaves on the day: not counted
        _emp("E3", "D01", "2020-01-01", exit_="2026-10-05"),                         # leaves later: counted
        _emp("E4", "D01", "2026-10-01", hire="2026-10-01"),                          # hired after: not counted
    ])
    got = expected_q1(employee)
    assert dict(zip(got.department_id, got.headcount)) == {"D01": 1, "D02": 1}


def test_q2_sums_cost_and_counts_people_once():
    payroll = pd.DataFrame({
        "period_year": [2026, 2026, 2026, 2026], "period_month": [5, 5, 6, 8],
        "department_id": ["D01", "D01", "D01", "D01"], "employee_id": ["E1", "E2", "E1", "E1"],
        "employer_cost": [100.0, 50.0, 70.0, 999.0]})
    got = expected_q2(payroll)
    assert got.to_dict("records") == [
        {"year_month": "2026-05", "department_id": "D01", "employees_paid": 2, "employer_cost": 150.0},
        {"year_month": "2026-06", "department_id": "D01", "employees_paid": 1, "employer_cost": 70.0}]


def test_same_reports_missing_rows_and_value_differences():
    got = pd.DataFrame({"k": ["a", "b"], "v": [1.0, 2.0]})
    want = pd.DataFrame({"k": ["b", "c"], "v": [2.5, 3.0]})
    problems = _same(got, want, ["k"], {"v": 0.01})
    assert any("only in SQL" in p and "'a'" in p for p in problems)
    assert any("only in pandas" in p and "'c'" in p for p in problems)
    assert any("v differs" in p and "'b'" in p for p in problems)


def test_same_accepts_values_within_tolerance():
    a = pd.DataFrame({"k": ["a"], "v": [1.000]})
    b = pd.DataFrame({"k": ["a"], "v": [1.004]})
    assert _same(a, b, ["k"], {"v": 0.01}) == []
