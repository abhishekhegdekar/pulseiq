import pandas as pd

from pulseiq.leave_analysis import approved, by_status, dept_leave, start_weekday


def _lv(rows):
    df = pd.DataFrame(rows, columns=["leave_request_id", "employee_id", "leave_type_code", "start_date", "end_date", "days", "status"])
    df["start_date"] = pd.to_datetime(df.start_date)
    df["end_date"] = pd.to_datetime(df.end_date)
    return df


def test_only_approved_counts():
    lv = _lv([("1", "E1", "CL", "2026-01-05", "2026-01-05", 1, "Approved"),
              ("2", "E1", "CL", "2026-01-06", "2026-01-06", 1, "Rejected")])
    assert len(approved(lv)) == 1
    assert set(by_status(lv).status) == {"Approved", "Rejected"}


def test_leave_past_window_is_cut_and_prorated():
    lv = _lv([("1", "E1", "ML", "2026-09-01", "2026-09-30", 22, "Approved"),
              ("2", "E2", "ML", "2026-09-15", "2026-10-14", 22, "Approved")])
    a = approved(lv, pd.Timestamp("2026-09-30"))
    assert a.days.iloc[0] == 22
    assert a.days.iloc[1] == 12  # Sep 15-30 is 12 of its 22 working days


def test_weekday_excludes_maternity():
    lv = _lv([("1", "E1", "CL", "2026-01-05", "2026-01-05", 1, "Approved"),  # Monday
              ("2", "E1", "ML", "2026-01-07", "2026-06-30", 120, "Approved")])
    w = start_weekday(lv).set_index("weekday")
    assert w.loc["Mon", "leave_starts"] == 1 and w.loc["Wed", "leave_starts"] == 0


def test_small_department_blank():
    lv = _lv([("1", "E1", "CL", "2026-01-05", "2026-01-05", 1, "Approved")])
    emp = pd.DataFrame({"employee_id": ["E1"], "department_id": ["D1"]})
    att = pd.DataFrame({"employee_id": ["E1"], "department_id": ["D1"]})
    assert pd.isna(dept_leave(lv, att, emp).days_per_emp_month.iloc[0])
