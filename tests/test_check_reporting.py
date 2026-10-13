"""Tests for the pure pandas helpers in pulseiq.check_reporting (no database needed)."""
import pandas as pd

from pulseiq.check_reporting import diff, expected_current, expected_flow, expected_headcount

T = pd.Timestamp


def _employee():
    # E1 hired 2024-01-10, still employed.  E2 hired 2025-02-05, left 2025-04-20.
    # E3 hired 2022-06-01, moved dept 10 -> 20 on 2025-03-15.
    return pd.DataFrame({
        "employee_id": ["E1", "E2", "E3", "E3"],
        "hire_date": [T("2024-01-10"), T("2025-02-05"), T("2022-06-01"), T("2022-06-01")],
        "exit_date": [pd.NaT, T("2025-04-20"), pd.NaT, pd.NaT],
        "valid_from": [T("2024-01-10"), T("2025-02-05"), T("2022-06-01"), T("2025-03-15")],
        "department_id": [10, 10, 10, 20],
        "job_level": [2, 3, 2, 2],
    })


def test_headcount_uses_month_end_department_and_exit_rule():
    e = _employee()
    hc = expected_headcount(e, [T("2025-02-28"), T("2025-03-31"), T("2025-04-30")])
    got = {(str(r.month_end_date), r.department_id): r.headcount for r in hc.itertuples()}
    assert got[("2025-02-28", 10)] == 3          # E1, E2, E3
    assert got[("2025-03-31", 10)] == 2          # E3 has moved to 20
    assert got[("2025-03-31", 20)] == 1
    assert got[("2025-04-30", 10)] == 1          # E2 left on 04-20


def test_current_tenure_bands():
    cur = expected_current(_employee(), T("2025-06-30"))
    assert len(cur) == 2
    bands = dict(zip(cur.index, cur.tenure_band))
    assert bands["E1"] == "1 to under 3 years"
    assert bands["E3"] == "3 to under 5 years"


def test_flow_assigns_department_as_of_event_date():
    f = expected_flow(_employee(), T("2025-02-28"), T("2025-04-30"))
    row = f[(f.department_id == 10) & (f.month_end_date.astype(str) == "2025-04-30")].iloc[0]
    assert row.leavers == 1 and row.joiners == 0
    feb = f[f.month_end_date.astype(str) == "2025-02-28"]
    assert feb.joiners.sum() == 1


def test_diff_reports_only_real_differences():
    a = pd.DataFrame({"k": [1, 2], "n": [5, 6]})
    assert diff(a, a.copy(), ["k"], ["n"]) == []
    b = pd.DataFrame({"k": [1, 2], "n": [5, 7]})
    out = diff(a, b, ["k"], ["n"])
    assert len(out) == 1 and "view=6" in out[0] and "expected=7" in out[0]
