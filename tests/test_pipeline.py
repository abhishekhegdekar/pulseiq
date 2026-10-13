"""Tests for the PulseIQ ETL: valid input, deliberately invalid input, repeated runs.

Fixtures are tiny synthetic frames built in code (clearly fake data), so the tests
need no real workbook and no employee data.
"""
import json
from datetime import date

import pandas as pd
import pytest

from pulseiq.__main__ import main
from pulseiq.enrich import add_helper_columns
from pulseiq.extract import SOURCES
from pulseiq.publish import sha256_file
from pulseiq.transform import transform
from pulseiq.validate import build_schemas, validate

REPORTING = date(2026, 9, 30)
SCHEMAS = build_schemas(REPORTING)
D = pd.Timestamp


def employee_row(**kw):
    row = dict(employee_key=1, employee_id="EMP-0001", full_name="Asha Rao", gender="Female",
               date_of_birth=D("1990-01-01"), hire_date=D("2020-01-15"), exit_date=pd.NaT,
               employment_status="Active", employment_type="Permanent", department_id="D01",
               role_id="R002", role_title="Engineer", job_level=1, manager_id="EMP-0009",
               work_location="Pune", work_mode="Hybrid", highest_education="B.E.",
               valid_from=D("2020-01-15"), valid_to=D("2099-12-31"), is_current="Y",
               change_reason="Joining")
    return {**row, **kw}


def payroll_row(**kw):
    row = dict(payroll_item_id="PI-1", run_id="PR-2026-01", employee_id="EMP-0001", date_key=20260131,
               employee_key=1, period_end_date=D("2026-01-31"), department_id="D01", role_id="R002",
               payable_days=31.0, lop_days=0.0, overtime_hours_paid=0.0, variable_pay_type=None,
               monthly_fixed_gross=100000, basic=40000.0, hra=20000.0, conveyance=1600.0, medical=1250.0,
               special_allowance=37150.0, earned_fixed_pay=100000.0, overtime_pay=0.0, variable_pay=0.0,
               gross_pay=100000.0, pf_employee=1800.0, esi_employee=0.0, professional_tax=200, tds=5000.0,
               other_deductions=0, total_deductions=7000.0, net_pay=93000.0, pf_employer=1800.0,
               esi_employer=0.0, employer_cost=101800.0, headcount_flag=1)
    return {**row, **kw}


def attendance_row(**kw):
    row = dict(attendance_fact_id="FA-1", employee_id="EMP-0001", date_key=20260131, employee_key=1,
               department_id="D01", scheduled_days=20, present_days=20, wfh_days=0, half_days_unpaid=0,
               paid_leave_days=0, unpaid_absence_days=0, late_arrivals=0, avg_hours_worked=8.5,
               overtime_hours=0.0, attendance_rate=1.0, period_end_date=D("2026-01-31"))
    return {**row, **kw}


def leave_row(**kw):
    row = dict(leave_request_id="LR-1", employee_id="EMP-0001", employee_key=1, leave_type_code="CL",
               start_date_key=20260105, end_date_key=20260106, start_date=D("2026-01-05"),
               end_date=D("2026-01-06"), days=2, status="Approved", applied_on=D("2026-01-02"),
               decided_on=D("2026-01-03"), approver_id="EMP-0002", reason="Personal")
    return {**row, **kw}


ROWS = {"employee": employee_row, "payroll": payroll_row, "attendance": attendance_row, "leave": leave_row}


def frame(name, *overrides):
    return pd.DataFrame([ROWS[name](**o) for o in (overrides or [{}])])


def run(name, df, keys=frozenset({1})):
    transformed, stats = transform(name, df)
    return validate(name, transformed, stats, SCHEMAS[name], None if name == "employee" else set(keys))


def reasons(rejected):
    return " | ".join(rejected["reject_reason"])


# ---------- row-level rules: deliberately invalid data ----------

def test_valid_rows_pass_unchanged():
    clean, rejected, stats = run("payroll", frame("payroll"))
    assert len(clean) == 1 and rejected.empty
    assert stats == {"rows_in": 1, "duplicates_removed": 0, "rows_rejected": 0, "rows_out": 1}


def test_negative_salary_is_rejected_with_reason():
    clean, rejected, _ = run("payroll", frame("payroll", {"basic": -5.0}))
    assert clean.empty and "basic: greater_than_or_equal_to(0)" in reasons(rejected)


def test_missing_salary_is_rejected_not_filled_with_zero():
    clean, rejected, _ = run("payroll", frame("payroll", {"monthly_fixed_gross": None}))
    assert clean.empty
    assert "monthly_fixed_gross: not_nullable" in reasons(rejected)
    assert rejected["monthly_fixed_gross"].isna().all()  # still missing, never 0


def test_exact_duplicate_is_removed_and_counted_separately():
    df = frame("payroll", {}, {"payroll_item_id": "PI-X"})  # same record, different row label
    clean, rejected, stats = run("payroll", df)
    assert len(clean) == 1 and rejected.empty
    assert stats["duplicates_removed"] == 1
    assert stats["rows_in"] == stats["rows_out"] + stats["rows_rejected"] + stats["duplicates_removed"]


def test_conflicting_duplicate_key_rejects_both_rows():
    df = frame("payroll", {}, {"payroll_item_id": "PI-2", "basic": 41000.0})
    clean, rejected, _ = run("payroll", df)
    assert clean.empty and len(rejected) == 2
    assert "duplicate key (employee_key, run_id)" in reasons(rejected)


def test_payroll_row_for_unknown_employee_is_rejected():
    clean, rejected, _ = run("payroll", frame("payroll", {"employee_key": -1}))
    assert clean.empty and "employee_key: not found among valid employees" in reasons(rejected)


def test_payroll_period_after_reporting_date_is_rejected():
    _, rejected, _ = run("payroll", frame("payroll", {"period_end_date": D("2026-12-31")}))
    assert "period_end_date" in reasons(rejected)


def test_joining_after_leaving_is_rejected_not_dropped_or_fixed():
    df = frame("employee", {"exit_date": D("2019-12-31")})
    clean, rejected, _ = run("employee", df)
    assert clean.empty and len(rejected) == 1
    assert "hire_date_after_exit_date" in reasons(rejected)
    assert rejected["hire_date"].iloc[0] == D("2020-01-15")  # original values preserved


def test_active_employee_with_empty_exit_date_is_valid():
    clean, rejected, _ = run("employee", frame("employee"))
    assert len(clean) == 1 and rejected.empty


def test_two_current_rows_for_one_employee_id_are_rejected():
    df = frame("employee", {}, {"employee_key": 2})
    _, rejected, _ = run("employee", df)
    assert "duplicate_current_employee_id" in reasons(rejected)


def test_repeated_employee_id_across_history_rows_is_allowed():
    df = frame("employee", {"is_current": "N", "valid_to": D("2021-01-14")},
               {"employee_key": 2, "valid_from": D("2021-01-15")})
    clean, rejected, _ = run("employee", df)
    assert len(clean) == 2 and rejected.empty


def test_leave_ending_before_it_starts_is_rejected_not_swapped():
    df = frame("leave", {"start_date": D("2026-01-06"), "end_date": D("2026-01-05")})
    clean, rejected, _ = run("leave", df)
    assert clean.empty and "end_date_before_start_date" in reasons(rejected)
    assert rejected["start_date"].iloc[0] == D("2026-01-06")  # dates not silently swapped


def test_pending_leave_without_decision_date_is_valid():
    clean, rejected, _ = run("leave", frame("leave", {"status": "Pending", "decided_on": pd.NaT}))
    assert len(clean) == 1 and rejected.empty


def test_attendance_rate_above_one_is_rejected():
    _, rejected, _ = run("attendance", frame("attendance", {"attendance_rate": 1.5}))
    assert "attendance_rate: in_range(0, 1)" in reasons(rejected)


def test_ambiguous_text_date_is_rejected_not_guessed():
    df = frame("employee")
    df["hire_date"] = df["hire_date"].astype(object)
    df.loc[0, "hire_date"] = "03/04/2020"  # could be 3 April or 4 March
    clean, rejected, _ = run("employee", df)
    assert clean.empty and "unparseable date in hire_date" in reasons(rejected)


def test_name_whitespace_is_trimmed_but_spelling_is_kept():
    clean, _, _ = run("employee", frame("employee", {"full_name": "  Abhishek   DSouza "}))
    assert clean["full_name"].iloc[0] == "Abhishek DSouza"


# ---------- tenure ----------

def test_tenure_uses_fixed_reporting_date_for_active_staff():
    clean, _, _ = run("employee", frame("employee"))
    out = add_helper_columns("employee", clean, REPORTING)
    assert out["tenure_days"].iloc[0] == (D(REPORTING) - D("2020-01-15")).days


def test_tenure_stops_at_exit_date_for_leavers():
    clean, _, _ = run("employee", frame("employee", {"exit_date": D("2022-01-15")}))
    out = add_helper_columns("employee", clean, REPORTING)
    assert out["tenure_days"].iloc[0] == (D("2022-01-15") - D("2020-01-15")).days


# ---------- end to end: exit codes, publication policy, repeatability ----------

def write_workbook(path, **overrides):
    with pd.ExcelWriter(path) as writer:
        for name, (sheet, _) in SOURCES.items():
            data = overrides.get(name, frame(name))
            data.to_excel(writer, sheet_name=sheet, index=False)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("INPUT_WORKBOOK", str(tmp_path / "in.xlsx"))
    monkeypatch.setenv("REPORTING_DATE", "2026-09-30")
    monkeypatch.setenv("ALLOW_REJECTS", "false")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    return tmp_path


def last_log(env):
    return json.loads((env / "logs" / "runs.jsonl").read_text().splitlines()[-1])


def test_valid_input_publishes_clean_files_and_logs_success(env):
    write_workbook(env / "in.xlsx")
    assert main() == 0
    assert sorted(p.name for p in (env / "data" / "clean").iterdir()) == [
        "attendance.parquet", "employee.parquet", "leave.parquet", "payroll.parquet"]
    record = last_log(env)
    assert record["status"] == "SUCCESS" and record["published"] is True
    assert record["totals"]["rows_in"] == 4 and record["totals"]["rows_rejected"] == 0
    assert not (env / "data" / "_staging").exists()


def test_invalid_input_fails_loudly_and_keeps_previous_good_output(env):
    write_workbook(env / "in.xlsx")
    assert main() == 0
    before = {p.name: sha256_file(p) for p in (env / "data" / "clean").iterdir()}

    write_workbook(env / "in.xlsx", payroll=frame("payroll", {"basic": -5.0}))
    assert main() == 1
    after = {p.name: sha256_file(p) for p in (env / "data" / "clean").iterdir()}
    assert after == before  # failed run did not replace good output
    rejected = pd.read_csv(env / "data" / "rejected" / "payroll_rejected.csv")
    assert len(rejected) == 1 and "basic" in rejected["reject_reason"].iloc[0]
    record = last_log(env)
    assert record["status"] == "FAILED_VALIDATION" and record["published"] is False
    assert record["totals"]["rows_rejected"] == 1


def test_override_publishes_clean_rows_and_still_saves_rejects(env, monkeypatch):
    monkeypatch.setenv("ALLOW_REJECTS", "true")
    write_workbook(env / "in.xlsx", payroll=frame("payroll", {}, {"payroll_item_id": "PI-9", "employee_key": 7}))
    assert main() == 0
    assert last_log(env)["status"] == "SUCCESS_WITH_REJECTS_OVERRIDE"
    assert len(pd.read_parquet(env / "data" / "clean" / "payroll.parquet")) == 1
    assert len(pd.read_csv(env / "data" / "rejected" / "payroll_rejected.csv")) == 1


def test_missing_workbook_is_a_structural_failure_with_exit_code_2(env):
    assert main() == 2
    assert last_log(env)["status"] == "FAILED_STRUCTURAL_OR_CONFIG"


def test_missing_column_is_a_structural_failure_with_exit_code_2(env):
    write_workbook(env / "in.xlsx", leave=frame("leave").drop(columns=["days"]))
    assert main() == 2
    assert "days" in last_log(env)["error"]


def test_bad_reporting_date_is_a_config_failure_with_exit_code_2(env, monkeypatch):
    write_workbook(env / "in.xlsx")
    monkeypatch.setenv("REPORTING_DATE", "30-09-2026")
    assert main() == 2


def test_repeated_runs_give_identical_clean_files_but_new_run_ids(env):
    write_workbook(env / "in.xlsx")
    assert main() == 0
    first = {p.name: sha256_file(p) for p in (env / "data" / "clean").iterdir()}
    assert main() == 0
    second = {p.name: sha256_file(p) for p in (env / "data" / "clean").iterdir()}
    assert first == second
    lines = [json.loads(x) for x in (env / "logs" / "runs.jsonl").read_text().splitlines()]
    assert len(lines) == 2
    assert lines[0]["output_fingerprint"] == lines[1]["output_fingerprint"]
