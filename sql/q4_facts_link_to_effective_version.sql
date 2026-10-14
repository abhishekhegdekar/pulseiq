-- Q4 (integrity). Does every payroll / attendance row point at the employee version that was
-- effective in its month (latest valid_from <= period end), with matching department and role?
-- Expected: key_differs = 0 and attrs_differ = 0. outside_window is information only
-- (leavers' final months fall after the version's valid_to; the as-of rule still applies).
WITH rows_ AS (
    SELECT 'payroll' AS fact, f.employee_key, dt.date AS period_end, fe.employee_id,
           f.department_id, f.role_id
    FROM fact_payroll f
    JOIN dim_date dt ON dt.date_key = f.date_key
    JOIN dim_employee fe ON fe.employee_key = f.employee_key
    UNION ALL
    SELECT 'attendance', a.employee_key, dt.date, fe.employee_id, a.department_id, NULL
    FROM fact_attendance_monthly a
    JOIN dim_date dt ON dt.date_key = a.date_key
    JOIN dim_employee fe ON fe.employee_key = a.employee_key
), effective AS (
    SELECT r.*, v.employee_key AS effective_key, v.department_id AS v_dept, v.role_id AS v_role, v.valid_to
    FROM rows_ r
    JOIN LATERAL (
        SELECT * FROM dim_employee v
        WHERE v.employee_id = r.employee_id AND v.valid_from <= r.period_end
        ORDER BY v.valid_from DESC LIMIT 1
    ) v ON TRUE
)
SELECT fact,
       count(*)                                                   AS fact_rows,
       count(*) FILTER (WHERE employee_key <> effective_key)      AS key_differs,
       count(*) FILTER (WHERE department_id <> v_dept
                           OR (role_id IS NOT NULL AND role_id <> v_role)) AS attrs_differ,
       count(*) FILTER (WHERE period_end > valid_to)              AS outside_window
FROM effective
GROUP BY fact
ORDER BY fact;
