# Warehouse design (Task 2) - agreed decisions

## Business questions the warehouse must answer
1. Headcount by department by month.
2. Payroll cost by department / role by month.
3. Attendance rate and leave-without-pay days by department by month.
4. Which employees moved department (e.g. Sales -> Support in June)?

## Grain of each fact
- fact_payroll: one row per employee_key per payroll run (month).
- fact_attendance: one row per employee_key per date_key.
- fact_leave: one row per leave request.
- fact_headcount_monthly: one row per employee_id per month-end (derived from dim_employee).

## Dimension history (SCD Type 2)
dim_employee keeps one row per version: surrogate `employee_key`, natural `employee_id`,
`valid_from`, `valid_to`. Facts point at the surrogate key, so old facts keep the
department/role the employee had at the time.

## Rules agreed
- As-of rule: the version used for a period is the latest `valid_from` <= period end.
- Month-end convention: an employee belongs to the department they have at month end.
- People are counted with distinct employee_id, never rows.
- Overlapping versions: warning, not rejection.
- Cost per head needs a paid-employee denominator (444 paid vs 441 employed in Sep 2026).
