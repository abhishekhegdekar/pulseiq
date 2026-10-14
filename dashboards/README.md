# Dashboard export: Headcount & Departments

Exported from Superset 6.1.0 on 2026-10-14. The folder `headcount_departments/` holds the dashboard, its 7 charts, 3 datasets and the database definition (YAML).

- The database password is NOT stored. The export masks it as XXXXXXXXXX.
- All three datasets read the `reporting` views (sql/02_reporting_views.sql) through the read-only login `superset_ro`.
- Every number on the dashboard was compared with SQL: see sql/q5_dashboard_numbers.sql.

To restore into a fresh Superset: zip the folder (cd dashboards; zip -r headcount_departments.zip headcount_departments), then in Superset use Dashboards, then the import icon, choose the zip and enter the superset_ro password from .env when asked.
