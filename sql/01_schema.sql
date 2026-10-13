-- PulseIQ warehouse schema (star schema). Safe to re-run: every statement is IF NOT EXISTS.
-- Load order: dim_department, dim_leave_type, dim_date, dim_role, dim_employee, then facts.

-- ---------- Dimensions ----------
CREATE TABLE IF NOT EXISTS dim_department (
    department_id   text PRIMARY KEY,
    department_name text NOT NULL,
    cost_center     text NOT NULL,
    description     text NOT NULL,
    is_leadership   char(1) NOT NULL CHECK (is_leadership IN ('Y','N'))
);

CREATE TABLE IF NOT EXISTS dim_leave_type (
    leave_type_code        text PRIMARY KEY,
    leave_type_name        text NOT NULL,
    pay_type               text NOT NULL,
    annual_quota_days      integer NOT NULL CHECK (annual_quota_days >= 0),
    prorated_for_joiners   char(1) NOT NULL CHECK (prorated_for_joiners IN ('Y','N')),
    carry_forward_allowed  char(1) NOT NULL CHECK (carry_forward_allowed IN ('Y','N')),
    max_carry_forward_days integer NOT NULL CHECK (max_carry_forward_days >= 0),
    policy_note            text NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_date (
    date_key           integer PRIMARY KEY,          -- yyyymmdd
    date               date NOT NULL UNIQUE,
    year               integer NOT NULL,
    quarter            integer NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    month_number       integer NOT NULL CHECK (month_number BETWEEN 1 AND 12),
    month_name         text NOT NULL,
    year_month         char(7) NOT NULL,             -- 'yyyy-mm'
    week_of_year       integer NOT NULL,
    day_of_week        text NOT NULL,
    is_weekend         char(1) NOT NULL CHECK (is_weekend IN ('Y','N')),
    is_holiday         char(1) NOT NULL CHECK (is_holiday IN ('Y','N')),
    is_working_day     char(1) NOT NULL CHECK (is_working_day IN ('Y','N')),
    financial_year     text NOT NULL,
    fiscal_quarter     text NOT NULL,
    fiscal_month_number integer NOT NULL,
    is_month_end       char(1) NOT NULL CHECK (is_month_end IN ('Y','N')),
    month_start_date   date NOT NULL,
    month_end_date     date NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_role (
    role_id             text PRIMARY KEY,
    department_id       text NOT NULL REFERENCES dim_department,
    role_title          text NOT NULL,
    level               integer NOT NULL,
    grade               text NOT NULL,
    band_min_annual     integer NOT NULL,
    band_mid_annual     integer NOT NULL,
    band_max_annual     integer NOT NULL,
    overtime_eligible   char(1) NOT NULL CHECK (overtime_eligible IN ('Y','N')),
    band_reference_year integer NOT NULL,
    CHECK (band_min_annual <= band_mid_annual AND band_mid_annual <= band_max_annual)
);

-- SCD Type 2: one row per version of an employee.
-- employee_key = surrogate key (facts point here); employee_id = natural key (the person).
CREATE TABLE IF NOT EXISTS dim_employee (
    employee_key     integer PRIMARY KEY,
    employee_id      text NOT NULL,
    full_name        text NOT NULL,
    gender           text NOT NULL,
    date_of_birth    date NOT NULL,
    hire_date        date NOT NULL,
    exit_date        date,
    employment_status text NOT NULL,
    employment_type  text NOT NULL,
    department_id    text NOT NULL REFERENCES dim_department,
    role_id          text NOT NULL REFERENCES dim_role,
    role_title       text NOT NULL,
    job_level        integer NOT NULL,
    manager_id       text,
    work_location    text NOT NULL,
    work_mode        text NOT NULL,
    highest_education text NOT NULL,
    valid_from       date NOT NULL,
    valid_to         date NOT NULL,
    is_current       char(1) NOT NULL CHECK (is_current IN ('Y','N')),
    change_reason    text NOT NULL,
    CHECK (valid_from <= valid_to),
    UNIQUE (employee_id, valid_from)
);

-- ---------- Facts ----------
-- Grain: one row per employee version per payroll run (month).
CREATE TABLE IF NOT EXISTS fact_payroll (
    employee_key        integer NOT NULL REFERENCES dim_employee,
    run_id              text NOT NULL,
    payroll_item_id     text NOT NULL,
    employee_id         text NOT NULL,
    date_key            integer NOT NULL REFERENCES dim_date,
    department_id       text NOT NULL REFERENCES dim_department,
    role_id             text NOT NULL REFERENCES dim_role,
    payable_days        numeric(6,2) NOT NULL CHECK (payable_days >= 0),
    lop_days            numeric(6,2) NOT NULL CHECK (lop_days >= 0),
    overtime_hours_paid numeric(8,2) NOT NULL CHECK (overtime_hours_paid >= 0),
    variable_pay_type   text,
    monthly_fixed_gross numeric(12,2) NOT NULL CHECK (monthly_fixed_gross >= 0),
    basic               numeric(12,2) NOT NULL,
    hra                 numeric(12,2) NOT NULL,
    conveyance          numeric(12,2) NOT NULL,
    medical             numeric(12,2) NOT NULL,
    special_allowance   numeric(12,2) NOT NULL,
    earned_fixed_pay    numeric(12,2) NOT NULL,
    overtime_pay        numeric(12,2) NOT NULL,
    variable_pay        numeric(12,2) NOT NULL,
    gross_pay           numeric(12,2) NOT NULL,
    pf_employee         numeric(12,2) NOT NULL,
    esi_employee        numeric(12,2) NOT NULL,
    professional_tax    numeric(12,2) NOT NULL,
    tds                 numeric(12,2) NOT NULL,
    other_deductions    numeric(12,2) NOT NULL,
    total_deductions    numeric(12,2) NOT NULL,
    net_pay             numeric(12,2) NOT NULL,
    pf_employer         numeric(12,2) NOT NULL,
    esi_employer        numeric(12,2) NOT NULL,
    employer_cost       numeric(12,2) NOT NULL,
    headcount_flag      smallint NOT NULL,
    PRIMARY KEY (employee_key, run_id)
);

-- Grain: one row per employee version per month (monthly attendance summary).
CREATE TABLE IF NOT EXISTS fact_attendance (
    employee_key        integer NOT NULL REFERENCES dim_employee,
    date_key            integer NOT NULL REFERENCES dim_date,
    attendance_fact_id  text NOT NULL,
    employee_id         text NOT NULL,
    department_id       text NOT NULL REFERENCES dim_department,
    scheduled_days      integer NOT NULL CHECK (scheduled_days >= 0),
    present_days        integer NOT NULL CHECK (present_days >= 0),
    wfh_days            integer NOT NULL CHECK (wfh_days >= 0),
    half_days_unpaid    integer NOT NULL CHECK (half_days_unpaid >= 0),
    paid_leave_days     integer NOT NULL CHECK (paid_leave_days >= 0),
    unpaid_absence_days integer NOT NULL CHECK (unpaid_absence_days >= 0),
    late_arrivals       integer NOT NULL CHECK (late_arrivals >= 0),
    avg_hours_worked    numeric(5,2) NOT NULL,
    overtime_hours      numeric(6,2) NOT NULL,
    attendance_rate     numeric(5,4) NOT NULL CHECK (attendance_rate BETWEEN 0 AND 1),
    PRIMARY KEY (employee_key, date_key)
);

-- Grain: one row per leave request.
CREATE TABLE IF NOT EXISTS fact_leave (
    leave_request_id text PRIMARY KEY,
    employee_key     integer NOT NULL REFERENCES dim_employee,
    employee_id      text NOT NULL,
    leave_type_code  text NOT NULL REFERENCES dim_leave_type,
    start_date_key   integer NOT NULL REFERENCES dim_date,
    end_date_key     integer NOT NULL REFERENCES dim_date,
    start_date       date NOT NULL,
    end_date         date NOT NULL,
    days             numeric(5,1) NOT NULL CHECK (days > 0),
    status           text NOT NULL,
    applied_on       date NOT NULL,
    decided_on       date,
    approver_id      text,
    reason           text NOT NULL,
    CHECK (end_date >= start_date)
);

-- Grain: one row per employee per month-end while employed (derived from dim_employee).
CREATE TABLE IF NOT EXISTS fact_headcount_monthly (
    month_end_date date NOT NULL,
    employee_id    text NOT NULL,
    employee_key   integer NOT NULL REFERENCES dim_employee,
    department_id  text NOT NULL REFERENCES dim_department,
    role_id        text NOT NULL REFERENCES dim_role,
    PRIMARY KEY (employee_id, month_end_date)
);

-- ---------- Indexes (join keys and date filters; primary keys are indexed already) ----------
CREATE INDEX IF NOT EXISTS ix_employee_id          ON dim_employee (employee_id);
CREATE INDEX IF NOT EXISTS ix_employee_department  ON dim_employee (department_id);
CREATE INDEX IF NOT EXISTS ix_employee_current     ON dim_employee (employee_id) WHERE is_current = 'Y';
CREATE INDEX IF NOT EXISTS ix_role_department      ON dim_role (department_id);
CREATE INDEX IF NOT EXISTS ix_payroll_date         ON fact_payroll (date_key);
CREATE INDEX IF NOT EXISTS ix_payroll_department   ON fact_payroll (department_id, date_key);
CREATE INDEX IF NOT EXISTS ix_payroll_role         ON fact_payroll (role_id);
CREATE INDEX IF NOT EXISTS ix_attendance_date      ON fact_attendance (date_key);
CREATE INDEX IF NOT EXISTS ix_attendance_dept      ON fact_attendance (department_id, date_key);
CREATE INDEX IF NOT EXISTS ix_leave_employee       ON fact_leave (employee_key);
CREATE INDEX IF NOT EXISTS ix_leave_start          ON fact_leave (start_date_key);
CREATE INDEX IF NOT EXISTS ix_leave_type           ON fact_leave (leave_type_code);
CREATE INDEX IF NOT EXISTS ix_headcount_dept       ON fact_headcount_monthly (month_end_date, department_id);
