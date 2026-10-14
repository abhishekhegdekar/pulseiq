-- Q3. Attendance rate (M13) and leave-without-pay days (M15) by department, Sep 2026.
-- M13 = (SUM(present_days) + 0.5 * SUM(half_days_unpaid)) / SUM(scheduled_days)   (ratio of sums)
-- M15 = SUM(lop_days) from fact_payroll
-- Groups under 5 employees are flagged (metric dictionary minimum group size).
WITH att AS (
    SELECT a.department_id,
           count(DISTINCT a.employee_id) AS employees,
           sum(a.scheduled_days)         AS scheduled_days,
           sum(a.present_days)           AS present_days,
           sum(a.half_days_unpaid)       AS half_days_unpaid
    FROM fact_attendance_monthly a
    JOIN dim_date dt ON dt.date_key = a.date_key
    WHERE dt.year_month = '2026-09'
    GROUP BY a.department_id
), lop AS (
    SELECT f.department_id, sum(f.lop_days) AS lop_days
    FROM fact_payroll f
    JOIN dim_date dt ON dt.date_key = f.date_key
    WHERE dt.year_month = '2026-09'
    GROUP BY f.department_id
)
SELECT dep.department_id,
       dep.department_name,
       att.employees,
       round((att.present_days + 0.5 * att.half_days_unpaid)::numeric / att.scheduled_days, 4) AS attendance_rate,
       COALESCE(lop.lop_days, 0) AS lop_days,
       att.employees < 5         AS below_min_group_size
FROM dim_department dep
JOIN att ON att.department_id = dep.department_id
LEFT JOIN lop ON lop.department_id = dep.department_id
ORDER BY dep.department_id;
