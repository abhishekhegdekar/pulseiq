# Keys, upserts, SCD Type 2 and department transfers

## Natural key vs surrogate key
- **Natural key** = the ID the business already uses. `employee_id` (EMP-0194) names the *person*.
- **Surrogate key** = an ID the warehouse owns, with no business meaning. `employee_key` names one
  *version* of that person (100650, 100651, 100652 are three versions of EMP-0194).
- Facts store `employee_key`, so each fact row is tied to the department and role the person had
  *then*. People are counted with `COUNT(DISTINCT employee_id)`, never by counting rows.

## Slowly Changing Dimension Type 2 (history by new rows)
When an attribute we want to track changes (department, role), we do not overwrite the row. We close
the old version (`valid_to`) and add a new one (`valid_from`). Real example from the data:

| employee_key | employee_id | department | role | valid_from | valid_to | change_reason |
|---|---|---|---|---|---|---|
| 100650 | EMP-0194 | D03 Data & AI | R018 | 2020-09-14 | 2023-03-15 | Joining |
| 100651 | EMP-0194 | D03 Data & AI | R018 | 2023-03-16 | 2026-02-03 | Manager Exit / Reassignment |
| 100652 | EMP-0194 | D02 Product & Design | R012 | 2026-02-04 | 9999-12-31 | Transfer |

(`9999-12-31` means "still current".) Her payroll rows follow the version, not today's department:

| payroll month | employee_key | department | employer_cost |
|---|---|---|---|
| 2026-01 | 100651 | D03 | 160,479.00 |
| 2026-02 | 100652 | D02 | 154,811.89 |
| 2026-03 | 100652 | D02 | 160,479.00 |

## Upserts (why repeat loads are safe)
An upsert is "insert if new, update if changed, do nothing if identical" in one statement
(`INSERT ... ON CONFLICT (key) DO UPDATE ... WHERE values are different`).
- Facts have natural grains as primary keys (payroll: `employee_key + run_id`, attendance:
  `employee_key + date_key`, leave: `leave_request_id`), so loading twice cannot create a second copy.
- `dim_employee` has `UNIQUE (employee_id, valid_from)`: the same version arriving again is
  recognised and left alone. A new version row appears only when the source really contains one.
- Verified: second load = 0 inserted, 0 updated, everything unchanged.

## Rule for linking facts to history
A fact for a month uses the employee version with the **latest `valid_from` on or before that month's end**
(month-end convention). Check Q4 (`sql/q4_facts_link_to_effective_version.sql`) confirms it for all
7,340 payroll and 7,343 attendance rows: 0 rows point at the wrong version, 0 have a different
department or role. (82 payroll / 85 attendance rows fall after the version's `valid_to`: these are
leavers' final months; the rule still gives one clear answer.)

## What if someone moves Sales -> Support in June?
Rule: **May is reported under Sales, July under Support, and June under Support** (the month-end
department, because the move happened on or before 30 June).
- May payroll row -> version valid in May (Sales); stays in Sales forever, even after the transfer.
- July payroll row -> new version (Support).
- June is one monthly payroll amount; the source has no daily cost split, so we do not invent one.
  Reporting June in Sales (start-of-month) or splitting by days are alternatives, but they need a
  business decision and day-level data. We state the convention instead of hiding it.
- Headcount follows the same rule: the person counts once in June, in Support.
- Totals are safe: each employee-month is counted exactly once, so company totals never change,
  only the department split does.
In this data set there is **no Sales -> Support move in June** (the only Sales moves are D04 -> D02 and
D04 -> D03); the rule above is demonstrated with real transfers instead (EMP-0194 on 4 Feb 2026,
EMP-0274 on 30 Mar 2026), which the checks cover.

## Limitations of the source
- Only 19 department transfers exist in 1,606 versions; most versions are manager changes. Dates come
  from `valid_from` as provided: we cannot tell whether a transfer was entered late or backdated.
- No reliable *daily* history: facts are monthly, so mid-month moves cannot be split exactly.
- One employee has two versions with overlapping validity windows (logged as a warning); the as-of
  rule still gives a single answer.
- The loader never deletes dimension or fact rows. If the source drops or re-keys a row, the old row
  stays and is reported as `not_in_source`.
