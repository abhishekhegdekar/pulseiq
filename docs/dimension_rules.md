# Dimension sheets and cross-sheet rules (added in Step 13)

The pipeline now cleans 8 datasets: 4 dimensions (department, role, leave_type, date)
and 4 sources (employee, payroll, attendance, leave).

## Order of processing
department -> leave_type -> date -> role -> employee -> payroll -> attendance -> leave.
A dimension row that is rejected is *not* a valid reference, so facts pointing at it are
rejected too (cascade). Example: role D99 rejected -> employees with that role rejected ->
payroll rows of those employees rejected. Exit code 1 in strict mode.

## Rules added
| Rule | Applies to | Effect |
|---|---|---|
| Foreign key must exist among *valid* parent rows | employee -> department, role; role -> department; payroll/attendance/leave -> employee_key; payroll/attendance -> department, date; leave -> leave_type, start/end date | reject row |
| Fact department_id / role_id must equal the employee version it points at | payroll (both), attendance (department) | reject row |
| date_key must match the calendar date; working-day flag must be consistent | dim_date | reject row |
| Pay band min <= mid <= max | dim_role | reject row |
| Two versions of one employee with overlapping validity windows | dim_employee | **warning only** (logged in run record as `overlapping_versions`); real data has 1 |

## Decision
Warnings do not reject rows: overlap is a data-quality note for the owner of the HR extract,
and the as-of rule ("latest valid_from <= period end") still gives one answer per month.

## Tests
39 tests (25 original + 14 for the rules above). Each new check was mutation-tested:
disabling the reference check or the version-consistency check makes tests fail.
