# Attendance analysis: definitions (Task 4)

Status: agreed with the project owner on 2026-10-14. Every number in the attendance work must follow this page.

## 1. Source and grain

- Source table: `fact_attendance_monthly` (loaded as `fact_attendance`). One row per employee per month, Apr 2025 to Sep 2026 (18 months, 7,343 rows).
- There are **no daily records**. Anything that needs a day-level view (for example attendance by weekday) cannot be calculated. See section 7.
- Department: the `department_id` stored on the attendance row (the department the person belonged to in that month).
- Calendar: `dim_date` (`is_working_day`, `is_holiday`, `is_weekend`).

## 2. Headline metrics

| Metric | Formula | Notes |
|---|---|---|
| Attendance rate (M13) | (SUM(present_days) + 0.5 x SUM(half_days_unpaid)) / SUM(scheduled_days) | Pooled over all people in the group. Never an average of individual rates. |
| Late arrival rate (M14) | SUM(late_arrivals) / SUM(present_days) | Work-from-home days use web check-in time. |
| Paid leave share | SUM(paid_leave_days) / SUM(scheduled_days) | Explains part of the gap to 100%. |
| Unpaid absence share | (SUM(unpaid_absence_days) + 0.5 x SUM(half_days_unpaid)) / SUM(scheduled_days) | The other part of the gap. |
| Work-from-home share | SUM(wfh_days) / SUM(present_days) | WFH days count as present. |

Identity that must hold for every row: present + paid leave + unpaid absence + half days = scheduled days. The monthly check (section 8) tests it.

## 3. Denominator

- `scheduled_days` is the number of working days in the calendar month for that person. Weekends and public holidays are already excluded (it equals the `dim_date` working-day count for the month).
- Joiners and leavers have a shorter, pro-rated month. They stay in the data because they were really scheduled.
- Paid leave counts as **not present** (the M13 caveat in the metric dictionary).

## 4. Rows that are excluded, kept or flagged

| Case | Rows | Rule |
|---|---|---|
| Attendance recorded after the person left (DQ-01, `FA-X0001` to `FA-X0004`) | 4 | Excluded from every rate. Reported in the check output. |
| Employed in the month but no attendance row | 1 (Jan 2026) | Not imputed. Reported. Treated as missing, not as zero. |
| Zero days present | 35 | Kept. They are real absences and lower the rate. |
| Short months (under 15 scheduled days) | 164 | Kept. Weighted by their scheduled days automatically. |

## 5. Small groups

A department rate for a month is shown only if at least **5 employees** have an attendance row in that group and month (minimum group size for M13 and M14). Smaller groups are shown as blank, never as 0. The Executive Office (1 person) is therefore always blank at department level but is included in the company total.

## 6. Time views

- **Monthly**: company, department and department x month.
- **Rolling 3-month rate**: (sum of the numerators over the last 3 months) / (sum of the denominators over the same months). Shown only when all 3 months exist for the group, so the first two months of data (Apr, May 2025) have none.
- **December check**: Dec 2025 is compared with Nov 2025 and Jan 2026 for the company and for each department, to see whether the holiday month behaves differently (22 scheduled days, 1 holiday).

## 7. Leave analysis and the weekday view

- Leave types and their pay type come from `dim_leave_type`. Leave analysis uses `fact_leave` with status Approved only (Pending and Rejected are counted separately, not as leave taken).
- Leave rows with end date before start date (DQ-08, 2 rows) are corrected by swapping the dates, and reported.
- **Weekday view**: because attendance has no daily data, the weekday summary is replaced by "leave requests by the weekday the leave starts". It is labelled as leave starts, not as absences, and must not be read as attendance by weekday.

## 8. AI anomaly file (`fact_anomaly`)

- Source: model `iforest-attendance-0.1`, scored 2026-10-01. 221 rows are attendance flags (reason codes: PATTERN_SHIFT, NO_ATTENDANCE, LONG_UNPAID_ABSENCE, FREQUENT_LATE).
- **Join key: employee_id + month.** The file's `record_id` (`AF-…`) points at a feature table we do not have, so it cannot be joined to `fact_attendance` ids. All 221 flags match an attendance row on employee and month.
- **Reliability**: all 35 zero-present rows are flagged NO_ATTENDANCE, but 15 other NO_ATTENDANCE flags have days present, which contradicts the reason text "No presence recorded for the whole month".
- Use: shown only as a labelled "review list" for a human. Flags never change a rate, and no one is judged on a flag alone.
- If the file is missing or empty, the analysis still runs. Only tests may use a clearly labelled fixture, never the real analysis.

## 9. Checks that run every time

1. Row reconciliation: present + paid leave + unpaid absence + half days = scheduled days.
2. Stored `attendance_rate` equals the M13 formula (tolerance 0.0001).
3. Present days never exceed scheduled days. WFH days never exceed present days.
4. Scheduled days equal the `dim_date` working days for a full month.
5. No attendance after exit (the 4 known rows are excluded and counted).
6. Employed-in-month people without a row are listed.
7. Pooled company rate recomputed independently in pandas matches the SQL.
