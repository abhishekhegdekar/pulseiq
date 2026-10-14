import pandas as pd

from pulseiq.attendance_report import december_check, window_summary


def _rows(dept, n, month, present=20, sched=22):
    return [dict(employee_id=f"{dept}{i}", department_id=dept, period_end_date=pd.Timestamp(month),
                 scheduled_days=sched, present_days=present, wfh_days=0, half_days_unpaid=0,
                 paid_leave_days=sched - present, unpaid_absence_days=0, late_arrivals=1) for i in range(n)]


def test_window_blanks_small_department():
    att = pd.DataFrame(_rows("A", 6, "2026-01-31") + _rows("B", 2, "2026-01-31"))
    out = window_summary(att, "2026-01-31", "2026-01-31").set_index("department_id")
    assert out.loc["A", "attendance_rate"] == 20 / 22
    assert pd.isna(out.loc["B", "attendance_rate"])


def test_window_pools_months():
    att = pd.DataFrame(_rows("A", 5, "2026-01-31", present=22) + _rows("A", 5, "2026-02-28", present=11))
    out = window_summary(att, "2026-01-31", "2026-02-28").set_index("department_id")
    assert abs(out.loc["A", "attendance_rate"] - 0.75) < 1e-9


def test_december_check_has_three_months():
    rows = []
    for m in ("2025-11-30", "2025-12-31", "2026-01-31"):
        rows += _rows("A", 5, m)
    assert list(december_check(pd.DataFrame(rows)).index) == ["2025-11", "2025-12", "2026-01"]
