# Attendance definitions (Task 4)

Version 2. This replaces the first version, which wrongly said DQ-08 leave rows are corrected by swapping dates. Task 1 rejects them instead.

## 1. Source and grain
- `fact_attendance`: one row per employee per month. There is no daily data, so every figure is monthly.
- `scheduled_days` equals the working days in `dim_date` for that month (check A4).
- Every row satisfies: present + paid leave + unpaid absence + half-day-unpaid = scheduled (check A1).

## 2. Headline metrics
| Metric | Formula |
|---|---|
| Attendance rate (M13) | (SUM present_days + 0.5 x SUM half_days_unpaid) / SUM scheduled_days |
| Late arrival rate (M14) | SUM late_arrivals / SUM present_days |
| Paid leave share | SUM paid_leave_days / SUM scheduled_days |
| Unpaid absence share | SUM unpaid_absence_days / SUM scheduled_days |
| WFH share | SUM wfh_days / SUM present_days |

Paid leave counts as not present. Every group rate is pooled (sum over sum), never an average of employee rates.

## 3. Denominator
Scheduled working days only. Weekends and company holidays are not in `scheduled_days`, so they never lower the rate. Leave days stay in the denominator.

## 4. Rows excluded or kept
| Case | Rule |
|---|---|
| Attendance after the employee's exit (DQ-01, FA-X0001 to FA-X0004) | Excluded, listed in the log |
| Employed month with no attendance row (1 row, EMP-0566, Jan 2026) | Not imputed; listed in the log |
| Rows with zero present days (35) | Kept; they are real absences |
| Late rate when nobody was present | Left blank |

## 5. Small groups
A group with fewer than 5 employees is blanked, as with all PulseIQ metrics. The Executive Office is blank for that reason.

## 6. Time views
- Monthly company and department.
- Rolling 3-month: pooled over three consecutive months. Blank if a month is missing, and blank if the latest of the three months has fewer than 5 employees.
- December check: Dec 2025 compared with Nov 2025 and Jan 2026.

## 7. Leave analysis
- Source: the 3,439 clean leave rows. The 2 DQ-08 rows were rejected by Task 1 and are not used.
- Statuses are Approved, Rejected, Cancelled and Pending. Only Approved counts as leave taken. The others are reported separately.
- There is no daily attendance, so a weekday view of absence is not possible. The weekday of the leave start date is shown instead and labelled as a proxy.

## 8. Anomaly file
- Joined on employee_id + month only.
- 15 rows are flagged NO_ATTENDANCE although attendance exists. They contradict our data.
- Used only as a review list. It never changes a metric.

## 9. Checks run every time
A1 rows reconcile. A2 stored rate equals the M13 formula. A3 present <= scheduled and wfh <= present. A4 scheduled days equal calendar working days. A5 rate + paid share + unpaid share = 1. A6 pooled monthly rate equals the weighted stored rate.
