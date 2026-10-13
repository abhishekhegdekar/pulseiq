-- Reporting layer for dashboards (Superset reads ONLY this schema).
-- No names, dates of birth or employee IDs are exposed: people are counted with COUNT(*) because each
-- row is one employee in one month (the primary key of fact_headcount_monthly is employee_id + month end).
-- Safe to re-run.
CREATE SCHEMA IF NOT EXISTS reporting;

-- One row per employed person per month-end (M01 Headcount = COUNT(*)).
CREATE OR REPLACE VIEW reporting.headcount_monthly AS
SELECT h.month_end_date,
       to_char(h.month_end_date, 'YYYY-MM') AS year_month,
       d.department_id,
       d.department_name,
       r.role_id,
       r.role_title,
       e.job_level
FROM fact_headcount_monthly h
JOIN dim_department d ON d.department_id = h.department_id
JOIN dim_role r       ON r.role_id = h.role_id
JOIN dim_employee e   ON e.employee_key = h.employee_key;

-- One row per person employed at the latest month-end, with tenure (L01) and tenure band.
-- Tenure = years from hire date to the as-of date (days / 365.25).
CREATE OR REPLACE VIEW reporting.current_employees AS
WITH latest AS (
    SELECT max(month_end_date) AS as_of_date FROM fact_headcount_monthly
), hire AS (
    SELECT employee_id, min(hire_date) AS hire_date FROM dim_employee GROUP BY employee_id
), base AS (
    SELECT l.as_of_date, d.department_id, d.department_name, r.role_id, r.role_title, e.job_level,
           (l.as_of_date - hire.hire_date) AS tenure_days
    FROM latest l
    JOIN fact_headcount_monthly h ON h.month_end_date = l.as_of_date
    JOIN hire                     ON hire.employee_id = h.employee_id
    JOIN dim_department d         ON d.department_id = h.department_id
    JOIN dim_role r               ON r.role_id = h.role_id
    JOIN dim_employee e           ON e.employee_key = h.employee_key
)
SELECT as_of_date, department_id, department_name, role_id, role_title, job_level,
       round(tenure_days / 365.25, 2) AS tenure_years,
       CASE WHEN tenure_days / 365.25 < 1  THEN 'Under 1 year'
            WHEN tenure_days / 365.25 < 3  THEN '1 to under 3 years'
            WHEN tenure_days / 365.25 < 5  THEN '3 to under 5 years'
            WHEN tenure_days / 365.25 < 10 THEN '5 to under 10 years'
            ELSE '10+ years' END AS tenure_band,
       CASE WHEN tenure_days / 365.25 < 1  THEN 1
            WHEN tenure_days / 365.25 < 3  THEN 2
            WHEN tenure_days / 365.25 < 5  THEN 3
            WHEN tenure_days / 365.25 < 10 THEN 4
            ELSE 5 END AS tenure_band_order
FROM base;

-- Joiners (hire date in the month) and leavers (exit date in the month) per month and department.
-- The department is the one the person had on the event date (latest version with valid_from <= date).
-- Months covered = the months of fact_headcount_monthly. Company-wide, net_change equals the change in headcount since the previous month-end.
CREATE OR REPLACE VIEW reporting.joiners_leavers_monthly AS
WITH person AS (
    SELECT employee_id, min(hire_date) AS hire_date, max(exit_date) AS exit_date
    FROM dim_employee GROUP BY employee_id
), asof AS (
    SELECT min(month_end_date) AS first_date, max(month_end_date) AS as_of_date FROM fact_headcount_monthly
), events AS (
    SELECT employee_id, hire_date AS event_date, 1 AS joiner, 0 AS leaver FROM person
    UNION ALL
    SELECT employee_id, exit_date, 0, 1 FROM person WHERE exit_date IS NOT NULL
), scoped AS (
    SELECT ev.*, (date_trunc('month', ev.event_date) + interval '1 month - 1 day')::date AS month_end_date
    FROM events ev CROSS JOIN asof
    WHERE ev.event_date <= asof.as_of_date
      AND ev.event_date >= date_trunc('month', asof.first_date)   -- same window as the headcount history
)
SELECT s.month_end_date,
       to_char(s.month_end_date, 'YYYY-MM') AS year_month,
       d.department_id,
       d.department_name,
       sum(s.joiner)::int                 AS joiners,
       sum(s.leaver)::int                 AS leavers,
       (sum(s.joiner) - sum(s.leaver))::int AS net_change
FROM scoped s
JOIN LATERAL (
    SELECT v.department_id FROM dim_employee v
    WHERE v.employee_id = s.employee_id AND v.valid_from <= s.event_date
    ORDER BY v.valid_from DESC LIMIT 1
) av ON TRUE
JOIN dim_department d ON d.department_id = av.department_id
GROUP BY s.month_end_date, d.department_id, d.department_name;
