# PulseIQ metric dictionary (first five metrics)

Status: **started in Task 1**. Metric IDs `M01`–`M15` come from the `metric_dictionary` sheet of
`03_PulseIQ_Analytics_Star_Schema_Dataset.xlsx` (the official definitions). That sheet has no filter,
denominator or missing-value columns, so this document adds them. `L01` is a **local** metric proposed
here because Task 3 needs tenure; it is not in the workbook's list.

All figures below are computed from the **clean** files in `data/clean/` (rows that passed validation;
the 2 exact duplicates and the 4 rejected rows are excluded). Reporting date: **30 Sep 2026**.
Chart titles in later tasks must use the metric names exactly as written here.

General rules for every metric
- Report **aggregates only**. Hide any group smaller than the minimum group size (5 in the official sheet).
- A missing value is never treated as 0. Required fields are validated; a row with a missing required value is rejected, not zero-filled.
- `dim_employee` keeps one row per *version* of a person (SCD Type 2). Count **people** (`COUNT(DISTINCT employee_id)`), never raw employee rows.

---

## M01 Headcount

| Field | Definition |
|---|---|
| Business definition | People employed on the last day of the month (permanent and fixed-term contract). |
| Formula | `COUNT(DISTINCT employee_id)` where `hire_date <= month_end` AND (`exit_date IS NULL` OR `exit_date > month_end`), using the employee version valid on `month_end` (`valid_from <= month_end <= valid_to`). |
| Grain | Month × department (department = the department of the version valid on month end). |
| Source | `data/clean/employee.parquet` (from `dim_employee`). Official sheet also lists `fact_headcount_monthly`. |
| Filters | None. All employment types and statuses. Official caveat: the CEO sits in department D00; exclude D00 only when comparing departments. |
| Denominator | Not applicable (a count). |
| Missing values | `hire_date` is required (row rejected if missing). An empty `exit_date` means still employed and counts as employed. Nothing is filled in. |
| Unit / direction | count / context dependent. |
| Edge case | `exit_date` is the last working day. Under the official formula a person whose `exit_date` equals the month end is **not** counted for that month end. |
| Check value | 441 people on 30 Sep 2026. Matches the workbook's separate `fact_headcount_monthly` total (441) and all 11 departments; also matched on 30 Apr 2025 (380), 31 Dec 2025 (398) and 30 Jun 2026 (417). |

"Current headcount" = M01 at the reporting date (30 Sep 2026).

## M09 Payroll cost (employer cost)

| Field | Definition |
|---|---|
| Business definition | Full cost of employees to the company: gross pay plus employer PF and ESI. |
| Formula | `SUM(employer_cost)` |
| Grain | Employee × month (reported by department × month, department taken from the employee version valid at the period end). |
| Source | `data/clean/payroll.parquet` (from `fact_payroll`). |
| Filters | Rows that passed validation only. All payroll runs in the file (Apr 2025 – Sep 2026). |
| Denominator | Not applicable (a sum). |
| Missing values | `employer_cost` is required and non-negative; a missing or negative value rejects the row. Never treated as 0. |
| Unit / direction | INR / lower is better when output is equal. |
| Caveat | Must later reconcile with ledger accounts 5001–5005 (not part of Task 1). |
| Check value | Sep 2026: ₹55,519,621.87 over 444 payroll rows. All 18 months: ₹861,586,392.42 over 7,340 rows. |

## M13 Attendance rate

| Field | Definition |
|---|---|
| Business definition | Days present (a half day counts 0.5) divided by scheduled working days. |
| Formula | `(SUM(present_days) + 0.5 × SUM(half_days_unpaid)) / SUM(scheduled_days)` |
| Grain | Employee × month in the source; reported by department × month. |
| Source | `data/clean/attendance.parquet` (from `fact_attendance_monthly`). |
| Filters | Rows that passed validation. |
| Denominator | `SUM(scheduled_days)`: working days scheduled in the month. Weekends and holidays are not in `scheduled_days`; Task 4 will confirm how holidays and leave are treated. |
| Missing values | Counts must be present and non-negative (else row rejected). If the summed denominator is 0 the rate is **undefined (NULL), not 0 or 100%**. |
| Unit / direction | ratio / higher is better. |
| Caveats | Paid leave counts as *not present* (official caveat). Always take a **ratio of sums**, never an average of the per-row `attendance_rate`. |
| Check value | Sep 2026: 95.19% (ratio of sums over 444 rows). The average of row rates gives 95.22%, which shows why the method matters. |

## M15 Leave without pay days

| Field | Definition |
|---|---|
| Business definition | Unpaid absence and unpaid leave days. |
| Formula | `SUM(lop_days)` from payroll. |
| Grain | Employee × month (reported by department × month). |
| Source | `data/clean/payroll.parquet`. |
| Filters | Rows that passed validation. |
| Denominator | Not applicable (a sum of days). |
| Missing values | `lop_days` is required and non-negative; a missing value rejects the row. A half-day unpaid counts 0.5. |
| Unit / direction | days / lower is better. |
| Check value | Sep 2026: 85.5 days. All 18 months: 1,595.0 days. |

## L01 Average tenure (years), local proposal

| Field | Definition |
|---|---|
| Business definition | Average length of service of the people employed at the reporting date. |
| Formula | `AVG(tenure_days) / 365.25` over distinct people employed on the reporting date, where `tenure_days = reporting_date − hire_date` (30 Sep 2026, never today's date). |
| Grain | Person, summarised by department or company. |
| Source | `data/clean/employee.parquet` helper columns `hire_date`, `tenure_days`. |
| Filters | People counted in M01 on the reporting date; one row per `employee_id`. Leavers are excluded (their tenure stops at `exit_date`). |
| Denominator | Number of people employed at the reporting date (M01). |
| Missing values | `hire_date` is required (row rejected if missing), so tenure is never missing. |
| Unit / direction | years / context dependent. |
| Caveat | `tenure_days` repeats on every history row of a person. Deduplicate by `employee_id` before averaging. Tenure *bands* are defined in Task 3. |
| Check value | 3.78 years across 441 people on 30 Sep 2026. |

---

Next metrics to add (already defined in the official sheet): M02 Hires, M03 Exits, M04 Attrition rate (monthly), M10 Cost per head, M14 Late arrival rate.
Cost per head note: its denominator is *paid* employees in the month, which can exceed headcount (444 paid vs 441 employed in Sep 2026, because some people are paid in the month they leave).
