-- Reproduces the numbers shown on the "Attendance & Leave" dashboard, straight from the reporting views.
-- Run: docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < sql/q6_attendance_dashboard_numbers.sql
-- Rates are pooled: SUM(numerator) / SUM(denominator). "Last 12 months" = the 12 months up to the latest month.

\echo '--- A. Company attendance rate (M13) by month: min, max, latest ---'
WITH m AS (
    SELECT month_end_date,
           (sum(present_days) + 0.5 * sum(half_days_unpaid)) / sum(scheduled_days) AS rate
    FROM reporting.attendance_monthly GROUP BY 1)
SELECT round(min(rate) * 100, 1) AS min_pct, round(max(rate) * 100, 1) AS max_pct,
       round((SELECT rate FROM m ORDER BY month_end_date DESC LIMIT 1) * 100, 1) AS latest_pct
FROM m;

\echo '--- B. M13 attendance rate by department, last 12 months ---'
SELECT department_name,
       round((sum(present_days) + 0.5 * sum(half_days_unpaid)) / sum(scheduled_days) * 100, 1) AS attendance_pct
FROM reporting.attendance_monthly
WHERE month_end_date > (SELECT max(month_end_date) FROM reporting.attendance_monthly) - interval '12 months'
GROUP BY 1 ORDER BY 2 DESC;

\echo '--- C. M14 late arrival rate by department, last 12 months ---'
SELECT department_name,
       round(sum(late_arrivals)::numeric / sum(present_days) * 100, 1) AS late_pct
FROM reporting.attendance_monthly
WHERE month_end_date > (SELECT max(month_end_date) FROM reporting.attendance_monthly) - interval '12 months'
GROUP BY 1 ORDER BY 2 DESC;

\echo '--- D. M14 company late rate by month: min, max ---'
SELECT round(min(r) * 100, 1) AS min_pct, round(max(r) * 100, 1) AS max_pct
FROM (SELECT sum(late_arrivals)::numeric / sum(present_days) AS r
      FROM reporting.attendance_monthly GROUP BY month_end_date) t;

\echo '--- E. Approved leave days by type ---'
SELECT leave_type_name, round(sum(days)) AS approved_days
FROM reporting.leave_by_type WHERE status = 'Approved' GROUP BY 1 ORDER BY 2;

\echo '--- F. Approved leave starts by weekday (maternity excluded) ---'
SELECT weekday_number, weekday, leave_starts FROM reporting.leave_start_weekday ORDER BY 1;

\echo '--- G. AI/ML flags by monthly-data check (total 221) ---'
SELECT monthly_data_check, sum(flagged_employee_months) AS flagged
FROM reporting.attendance_flags_monthly GROUP BY 1 ORDER BY 1;
