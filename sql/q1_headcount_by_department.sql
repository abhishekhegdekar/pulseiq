-- Q1. Headcount by department at 30 Sep 2026 (metric M01).
SELECT d.department_id,
       d.department_name,
       count(DISTINCT h.employee_id) AS headcount
FROM fact_headcount_monthly h
JOIN dim_department d ON d.department_id = h.department_id
WHERE h.month_end_date = DATE '2026-09-30'
GROUP BY d.department_id, d.department_name
ORDER BY d.department_id;
