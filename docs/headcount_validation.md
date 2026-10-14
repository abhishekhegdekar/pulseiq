# Headcount fact and validation

`fact_headcount_monthly` (grain: one row per employee per month-end while employed) is rebuilt
from `dim_employee` at the end of every load (`python -m pulseiq.load`).

## Rules
- Month ends come from `dim_date` (`is_month_end = 'Y'`) up to DEMO_TODAY.
- Employed at a month end: `hire_date <= month end` and (`exit_date` empty or `exit_date > month end`).
  A person who leaves on the last day of a month is NOT counted that month.
- Department and role: the latest `dim_employee` version with `valid_from <= month end` (as-of rule).
- Headcount = `count(DISTINCT employee_id)`, never row counts.

## Validation against the workbook
The workbook's own `fact_headcount_monthly` sheet is per department per month. Run:

    docker compose run --rm load python -m pulseiq.check_headcount

It compares `headcount_end` for all 891 department-months (81 months x 11 departments):
**all 891 agree (total 23,590)**. Mutation checks: counting the exit day as employed breaks 16
department-months; ignoring the as-of rule (using the first version) breaks 608.

## Derived table behaviour
This is the only table the loader may delete from: rows that no longer follow from `dim_employee`
are removed, because the table is fully determined by the dimension.
