# Cleaning, validation and publication rules (Task 1)

Agreed before they were applied. The code in `src/pulseiq/` implements exactly these rules.

## Dataset mapping
| Dataset | Workbook sheet | Key used for uniqueness |
|---|---|---|
| employee | `dim_employee` | `employee_key` (unique); `employee_id` is unique only among current rows (`is_current = Y`) because it repeats across history versions |
| payroll | `fact_payroll` | (`employee_key`, `run_id`). Salary figures are columns of this sheet; there is no separate salary file |
| attendance | `fact_attendance_monthly` | (`employee_key`, `date_key`) |
| leave | `fact_leave` | `leave_request_id` |

## A. Structural failures: stop the run (exit code 2)
Missing input file, missing sheet, missing required column, malformed setting (for example a date that is not `YYYY-MM-DD`), or a whole column of the wrong type. Nothing in `data/clean/` or `data/rejected/` changes.

## B. Row failures: reject with a reason
Saved to `data/rejected/<dataset>_rejected.csv` with `dataset`, `source_row` (row number in the Excel sheet) and `reject_reason`. Reasons name the column and the rule, never the value.
- employee_key not found among valid employees (this includes payroll/attendance/leave rows that point at a rejected employee version)
- negative salary/pay amounts; negative counts; attendance rate outside 0–1; leave `days` not above 0
- missing required value (including any salary column)
- unparseable or ambiguous date, or a date after the reporting date (hire, payroll period, attendance period)
- leave `end_date` before `start_date`
- `hire_date` after `exit_date`; `valid_from` after `valid_to`
- two *current* rows for one `employee_id`; duplicate employee_key; conflicting duplicate key (same key, different values: **both** rows rejected)

## C. Exact duplicates: removed and counted separately
Rows identical in every column except their row label (for example `payroll_item_id`) are the same record. The first is kept; the log reports `duplicates_removed`. Reconciliation per dataset: `rows_in = rows_out + rows_rejected + duplicates_removed` (the code raises an error if it does not hold).

## D. Missing values are never filled
Empty `exit_date` (still employed), empty `variable_pay_type` (no variable pay) and empty `decided_on` (Pending leave) keep their meaning. A missing salary is never replaced by 0; the row is rejected.

## E. Standardisation only
Trim spaces, collapse repeated spaces in `full_name`, blank text becomes missing. Spelling and capitalisation are kept (for example "DSouza"). Names are never used to match or deduplicate people (26 names are shared by different employee IDs). Dates must be real Excel dates or ISO `YYYY-MM-DD` text; `03/04/2020` is rejected, not guessed.

## F. Joining date after leaving date

**Rule: flag and reject. Do not drop silently and do not auto-fix.** The row goes to `data/rejected/employee_rejected.csv` with reason `hire_date_after_exit_date`, original values untouched, and under the default policy the run fails.

Why not the alternatives:
- **Fix** (swap the dates): we cannot know which of the two dates is wrong. A swap invents a tenure and a hire date the business never recorded.
- **Drop** silently: the person disappears from headcount, and their payroll, attendance and leave rows lose their employee. Costs would vanish without anyone noticing.
- **Keep as is**: negative tenure and an impossible employment period would flow into every dashboard.

Rejecting keeps the evidence, tells HR exactly which record to correct at the source, and the run can be repeated after the fix. Consequences to be aware of: facts that point at a rejected employee version are rejected too, so one bad employee row can reject many fact rows. `hire_date` equal to `exit_date` (a one-day stay) is allowed.
In the supplied workbook this never occurs (0 rows), so it is covered by automated tests with a deliberately broken row. The closest real cases are the 2 leave requests that end before they start.

## G. Fixed reporting date
Tenure and the "date after reporting date" check use `REPORTING_DATE` (30 Sep 2026, the workbook cut-off), never today's date. Same input therefore gives the same output on any day.

## Publication policy
| Outcome | Exit code | `data/clean/` | `data/rejected/` | Run log |
|---|---|---|---|---|
| No rejects | 0 `SUCCESS` | replaced | refreshed (headers only) | yes |
| Rejects, `ALLOW_REJECTS=true` | 0 `SUCCESS_WITH_REJECTS_OVERRIDE` | replaced | refreshed | yes |
| Rejects, strict (default) | 1 `FAILED_VALIDATION` | **untouched** | refreshed (evidence) | yes |
| Structural / config failure | 2 | untouched | untouched | yes |
| Unexpected bug | 3 | untouched | untouched | yes |

Files are written to `data/_staging/` first and swapped in by rename only when complete. If a run dies between the two renames, the next run restores the previous folder.

## Repeatability
Clean files contain no timestamps and are sorted by key, so identical input gives byte-identical files. The run log (`logs/runs.jsonl`) records a new `run_id`, `started_at` and `finished_at` on every run, and an `output_fingerprint` (hash of the clean files) that stays the same when the data is the same.
