import pandas as pd

from pulseiq.anomaly_review import claimed_days, join_flags, summary, supported, zero_present_coverage


def _flag(code, text="x", emp="E1", month="2026-01-31"):
    return dict(employee_id=emp, month=pd.Timestamp(month), reason_code=code, reason_text=text, record_id="AF-1")


def _att(emp="E1", month="2026-01-31", present=0, unpaid=0):
    return dict(attendance_fact_id="FA-1", employee_id=emp, period_end_date=pd.Timestamp(month),
                present_days=present, unpaid_absence_days=unpaid)


def test_claimed_days_parsed():
    assert claimed_days("13 consecutive unpaid absence days") == 13
    assert claimed_days("something else") is None


def test_no_attendance_supported_only_when_zero_present():
    j = join_flags(pd.DataFrame([_flag("NO_ATTENDANCE")]), pd.DataFrame([_att(present=0)]))
    assert supported(j.iloc[0]) is True
    j = join_flags(pd.DataFrame([_flag("NO_ATTENDANCE")]), pd.DataFrame([_att(present=20)]))
    assert supported(j.iloc[0]) is False


def test_long_unpaid_contradicted_when_monthly_days_too_few():
    f = pd.DataFrame([_flag("LONG_UNPAID_ABSENCE", "13 consecutive unpaid absence days")])
    j = join_flags(f, pd.DataFrame([_att(present=10, unpaid=5)]))
    assert supported(j.iloc[0]) is False


def test_pattern_shift_not_checkable_and_unmatched_flag_counted():
    j = join_flags(pd.DataFrame([_flag("PATTERN_SHIFT"), _flag("PATTERN_SHIFT", emp="E9")]), pd.DataFrame([_att(present=5)]))
    s = summary(j).iloc[0]
    assert s["flags"] == 2 and s["matched_to_attendance"] == 1 and s["contradicted"] == 1


def test_zero_present_coverage():
    att = pd.DataFrame([_att(present=0), _att(emp="E2", present=0)])
    flags = pd.DataFrame([_flag("NO_ATTENDANCE")])
    assert zero_present_coverage(att, flags) == (2, 1)
