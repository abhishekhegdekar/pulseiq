# Dashboard export: Headcount & Departments

Exported from Superset 6.1.0 on 2026-10-14. The folder `headcount_departments/` holds the dashboard, its 7 charts, 3 datasets and the database definition (YAML).

- The database password is NOT stored. The export masks it as XXXXXXXXXX.
- All three datasets read the `reporting` views (sql/02_reporting_views.sql) through the read-only login `superset_ro`.
- Every number on the dashboard was compared with SQL: see sql/q5_dashboard_numbers.sql.

To restore into a fresh Superset: zip the folder (cd dashboards; zip -r headcount_departments.zip headcount_departments), then in Superset use Dashboards, then the import icon, choose the zip and enter the superset_ro password from .env when asked.

# Dashboard export: Attendance & Leave

Exported from Superset 6.1.0 on 2026-10-14. The folder `attendance_leave/` holds the dashboard, its 8 charts, 5 datasets and the database definition (YAML).

- The database password is NOT stored. The export masks it as XXXXXXXXXX.
- All five datasets read the `reporting` views (sql/03_attendance_reporting.sql) through the read-only login `superset_ro`. No employee IDs reach Superset.
- The views are checked against the pandas calculations by `python -m pulseiq.check_attendance_reporting` (expected STATUS=ALL_MATCH).
- The Department filter applies to the attendance, late-arrival and AI-flag charts. The two leave charts are company-wide.
- Departments with fewer than 5 employees are hidden, and the one-person Executive Office is excluded.

To restore into a fresh Superset: zip the folder (cd dashboards; zip -r attendance_leave.zip attendance_leave), then in Superset use Dashboards, then the import icon, choose the zip and enter the superset_ro password from .env when asked.
