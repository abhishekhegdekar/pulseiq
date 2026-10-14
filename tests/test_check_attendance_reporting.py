import pandas as pd

from pulseiq.check_attendance_reporting import expected_flags, expected_leave, expected_monthly
from pulseiq.load import ANOMALY_COLUMNS, anomaly_frame


def _att(dept, n, month="2026-01-31"):
    return [dict(employee_id=f"{dept}{i}", department_id=dept, period_end_date=pd.Timestamp(month), scheduled_days=20,
                 present_days=19, wfh_days=5, half_days_unpaid=0, paid_leave_days=1, unpaid_absence_days=0,
                 late_arrivals=2) for i in range(n)]


def test_expected_monthly_leaves_out_small_departments():
    out = expected_monthly(pd.DataFrame(_att("A", 5) + _att("B", 4)))
    assert list(out.department_id) == ["A"] and out.present_days.iloc[0] == 95


def test_expected_leave_removes_cells_under_five_employees():
    rows = [dict(leave_request_id=f"L{i}", employee_id=f"E{i}", leave_type_code="CL", status="Approved",
                 start_date=pd.Timestamp("2026-01-05"), end_date=pd.Timestamp("2026-01-05"), days=1) for i in range(5)]
    rows += [dict(leave_request_id=f"M{i}", employee_id=f"E{i}", leave_type_code="ML", status="Approved",
                  start_date=pd.Timestamp("2026-01-05"), end_date=pd.Timestamp("2026-01-05"), days=1) for i in range(2)]
    out = expected_leave(pd.DataFrame(rows), pd.Timestamp("2026-09-30"))
    assert list(out.leave_type_code) == ["CL"] and out.days.iloc[0] == 5


def test_expected_flags_uses_kept_cells_only():
    att = pd.DataFrame(_att("A", 1) + _att("Z", 1))
    flags = pd.DataFrame([dict(employee_id="A0", month=pd.Timestamp("2026-01-31"), reason_code="NO_ATTENDANCE", reason_text="x"),
                          dict(employee_id="Z0", month=pd.Timestamp("2026-01-31"), reason_code="NO_ATTENDANCE", reason_text="x")])
    out = expected_flags(flags, att, {(pd.Timestamp("2026-01-31").date(), "A")})
    assert out.n.sum() == 1 and out.monthly_data_check.iloc[0] == "Contradicted"


def test_anomaly_frame_keeps_attendance_rows_and_month_end(tmp_path):
    sheet = pd.DataFrame({
        "result_id": ["AN-1", "AN-2"], "source_dataset": ["attendance_monthly_features", "payroll_monthly_features"],
        "record_id": ["AF-1", "PF-1"], "employee_id": ["E1", "E2"], "period": ["2026-01-01", "2026-01-01"],
        "anomaly_score": [0.9, 0.8], "flagged": ["Y", "Y"], "reason_code": ["NO_ATTENDANCE", "ZERO_PAY"],
        "reason_text": ["a", "b"], "money_at_risk": [None, 1.0], "model_version": ["m", "m"],
        "scored_at": ["2026-10-01 02:00:00", "2026-10-01 02:00:00"]})
    path = tmp_path / "w.xlsx"
    with pd.ExcelWriter(path) as xl:
        sheet.to_excel(xl, sheet_name="fact_anomaly", index=False)
    out = anomaly_frame(path)
    assert list(out.columns) == ANOMALY_COLUMNS and len(out) == 1
    assert out.period_end_date.iloc[0] == pd.Timestamp("2026-01-31")
