-- Every number on the "Headcount & Departments" dashboard, straight from the reporting views.
SELECT 'headcount' AS metric, count(*)::text AS value FROM reporting.current_employees
UNION ALL SELECT 'average_tenure_years', round(avg(tenure_years)::numeric, 2)::text FROM reporting.current_employees
UNION ALL SELECT 'dept_' || department_name, count(*)::text FROM reporting.current_employees GROUP BY department_name
UNION ALL SELECT 'tenure_' || tenure_band_order || '_' || tenure_band, count(*)::text FROM reporting.current_employees GROUP BY tenure_band_order, tenure_band
UNION ALL SELECT 'job_level_' || job_level, count(*)::text FROM reporting.current_employees GROUP BY job_level
UNION ALL SELECT 'trend_' || month_end_date, count(*)::text FROM reporting.headcount_monthly WHERE month_end_date >= DATE '2025-10-01' GROUP BY month_end_date
UNION ALL SELECT 'joiners_' || month_end_date, sum(joiners)::text FROM reporting.joiners_leavers_monthly WHERE month_end_date >= DATE '2025-10-01' GROUP BY month_end_date
UNION ALL SELECT 'leavers_' || month_end_date, sum(leavers)::text FROM reporting.joiners_leavers_monthly WHERE month_end_date >= DATE '2025-10-01' GROUP BY month_end_date
ORDER BY 1;
