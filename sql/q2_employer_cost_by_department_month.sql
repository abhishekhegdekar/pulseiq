-- Q2. Employer cost (metric M09) by department for May, June and July 2026.
-- The department comes from the payroll row, which points at the employee version
-- that was effective in that month, so a transfer moves cost from the month it takes effect.
SELECT dt.year_month,
       dep.department_id,
       dep.department_name,
       count(DISTINCT f.employee_id)  AS employees_paid,
       round(sum(f.employer_cost), 2) AS employer_cost
FROM fact_payroll f
JOIN dim_date dt       ON dt.date_key = f.date_key
JOIN dim_department dep ON dep.department_id = f.department_id
WHERE dt.year_month IN ('2026-05', '2026-06', '2026-07')
GROUP BY dt.year_month, dep.department_id, dep.department_name
ORDER BY dt.year_month, dep.department_id;
