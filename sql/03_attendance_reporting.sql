-- Attendance and leave reporting layer for dashboards (Superset reads ONLY the reporting schema).
-- Aggregates only: no names or employee IDs are exposed. Safe to re-run.
-- Rules (docs/attendance_definitions.md):
--   * attendance rows dated after the employee's exit month are excluded (known issue DQ-01)
--   * groups with fewer than 5 employees are left out (the Executive Office has 1 person)
--   * rates are computed by the dashboard as SUM(numerator) / SUM(denominator), never averaged
CREATE SCHEMA IF NOT EXISTS reporting;

-- AI/ML team's anomaly flags for attendance (workbook sheet fact_anomaly, source attendance_monthly_features).
-- Kept in the warehouse schema (not reporting): it holds employee IDs. Joined to attendance on employee_id + month.
CREATE TABLE IF NOT EXISTS fact_anomaly_attendance (
    result_id      text PRIMARY KEY,
    record_id      text NOT NULL,
    employee_id    text NOT NULL,
    period_end_date date NOT NULL,
    anomaly_score  numeric(5,3) NOT NULL CHECK (anomaly_score BETWEEN 0 AND 1),
    flagged        char(1) NOT NULL CHECK (flagged IN ('Y','N')),
    reason_code    text NOT NULL,
    reason_text    text NOT NULL,
    model_version  text NOT NULL,
    scored_date    date NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_anomaly_att_emp_month ON fact_anomaly_attendance (employee_id, period_end_date);

-- One row per month and department: summed day counts and the number of employees (M13, M14 inputs).
CREATE OR REPLACE VIEW reporting.attendance_monthly AS
WITH ex AS (
    SELECT employee_id, (date_trunc('month', max(exit_date)) + interval '1 month - 1 day')::date AS exit_month_end
    FROM dim_employee GROUP BY employee_id
)
SELECT dt.date AS month_end_date,
       to_char(dt.date, 'YYYY-MM') AS year_month,
       d.department_id,
       d.department_name,
       count(DISTINCT a.employee_id)::int AS employees,
       sum(a.scheduled_days)::int         AS scheduled_days,
       sum(a.present_days)::int           AS present_days,
       sum(a.wfh_days)::int               AS wfh_days,
       sum(a.half_days_unpaid)::int       AS half_days_unpaid,
       sum(a.paid_leave_days)::int        AS paid_leave_days,
       sum(a.unpaid_absence_days)::int    AS unpaid_absence_days,
       sum(a.late_arrivals)::int          AS late_arrivals
FROM fact_attendance_monthly a
JOIN dim_date dt       ON dt.date_key = a.date_key
JOIN dim_department d  ON d.department_id = a.department_id
LEFT JOIN ex           ON ex.employee_id = a.employee_id
WHERE ex.exit_month_end IS NULL OR dt.date <= ex.exit_month_end
GROUP BY dt.date, d.department_id, d.department_name
HAVING count(DISTINCT a.employee_id) >= 5;

-- Leave by type and status over the whole period (company level). Only Approved is leave taken.
-- Days of a leave that runs past the last attendance month are cut off and pro-rated by weekdays (Mon-Fri).
CREATE OR REPLACE VIEW reporting.leave_by_type AS
WITH win AS (
    SELECT max(dt.date) AS window_end FROM fact_attendance_monthly a JOIN dim_date dt ON dt.date_key = a.date_key
), cut AS (
    SELECT l.leave_request_id, l.employee_id, l.leave_type_code, l.status,
           CASE WHEN l.end_date <= w.window_end THEN l.days::numeric
                ELSE l.days::numeric
                     * (SELECT count(*) FROM generate_series(l.start_date, w.window_end, interval '1 day') g
                        WHERE extract(isodow FROM g) < 6)
                     / NULLIF((SELECT count(*) FROM generate_series(l.start_date, l.end_date, interval '1 day') g
                               WHERE extract(isodow FROM g) < 6), 0)
           END AS days_in_window
    FROM fact_leave l CROSS JOIN win w
)
SELECT t.leave_type_code, t.leave_type_name, t.pay_type, c.status,
       count(*)::int                       AS requests,
       count(DISTINCT c.employee_id)::int  AS employees,
       round(sum(c.days_in_window), 1)     AS days
FROM cut c JOIN dim_leave_type t ON t.leave_type_code = c.leave_type_code
GROUP BY t.leave_type_code, t.leave_type_name, t.pay_type, c.status
HAVING count(DISTINCT c.employee_id) >= 5;

-- The weekday a leave STARTS (Approved, maternity excluded). A proxy only: there is no daily attendance data.
CREATE OR REPLACE VIEW reporting.leave_start_weekday AS
SELECT extract(isodow FROM l.start_date)::int AS weekday_number,
       to_char(l.start_date, 'Dy')            AS weekday,
       count(*)::int                          AS leave_starts
FROM fact_leave l
WHERE l.status = 'Approved' AND l.leave_type_code <> 'ML'
GROUP BY 1, 2;

-- AI/ML attendance flags per month and department, with a check against our monthly attendance facts.
-- NO_ATTENDANCE is confirmed when present_days = 0; LONG_UNPAID_ABSENCE when unpaid absence days reach the
-- days the flag claims. Other reasons cannot be checked with monthly data.
CREATE OR REPLACE VIEW reporting.attendance_flags_monthly AS
SELECT f.period_end_date AS month_end_date,
       to_char(f.period_end_date, 'YYYY-MM') AS year_month,
       a.department_id,
       d.department_name,
       f.reason_code,
       CASE WHEN f.reason_code = 'NO_ATTENDANCE' THEN
                CASE WHEN a.present_days = 0 THEN 'Confirmed' ELSE 'Contradicted' END
            WHEN f.reason_code = 'LONG_UNPAID_ABSENCE'
                 AND substring(f.reason_text FROM '^\s*(\d+) consecutive unpaid absence days') IS NOT NULL THEN
                CASE WHEN a.unpaid_absence_days >=
                          substring(f.reason_text FROM '^\s*(\d+) consecutive unpaid absence days')::int
                     THEN 'Confirmed' ELSE 'Contradicted' END
            ELSE 'Not checkable' END AS monthly_data_check,
       count(*)::int AS flagged_employee_months
FROM fact_anomaly_attendance f
JOIN fact_attendance_monthly a ON a.employee_id = f.employee_id
JOIN dim_date dt       ON dt.date_key = a.date_key AND dt.date = f.period_end_date
JOIN dim_department d  ON d.department_id = a.department_id
WHERE f.flagged = 'Y'
  AND EXISTS (SELECT 1 FROM reporting.attendance_monthly m
              WHERE m.month_end_date = f.period_end_date AND m.department_id = a.department_id)
GROUP BY 1, 2, 3, 4, 5, 6;

-- Pooled rolling 3 months per department: the day counts of the month and the two before it, added up.
-- Dashboards compute the rate as SUM(numerator) / SUM(denominator) over these r_ columns, so the 3-month
-- figure is pooled, not an average of three monthly rates. Needs three consecutive months of data.
CREATE OR REPLACE VIEW reporting.attendance_rolling_3m AS
SELECT month_end_date, year_month, department_id, department_name, employees,
       r_scheduled_days, r_present_days, r_wfh_days, r_half_days_unpaid,
       r_paid_leave_days, r_unpaid_absence_days, r_late_arrivals
FROM (
    SELECT m.*,
           sum(scheduled_days)      OVER w AS r_scheduled_days,
           sum(present_days)        OVER w AS r_present_days,
           sum(wfh_days)            OVER w AS r_wfh_days,
           sum(half_days_unpaid)    OVER w AS r_half_days_unpaid,
           sum(paid_leave_days)     OVER w AS r_paid_leave_days,
           sum(unpaid_absence_days) OVER w AS r_unpaid_absence_days,
           sum(late_arrivals)       OVER w AS r_late_arrivals,
           count(*)                 OVER w AS n_months,
           min(month_end_date)      OVER w AS first_month
    FROM reporting.attendance_monthly m
    WINDOW w AS (PARTITION BY department_id ORDER BY month_end_date ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)
) s
WHERE n_months = 3
  AND first_month = (date_trunc('month', month_end_date) - interval '2 months' + interval '1 month - 1 day')::date;
