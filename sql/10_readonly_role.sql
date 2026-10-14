-- Read-only login for Superset. Run manually (needs the password as a psql variable):
--   docker compose exec -T db psql -U pulseiq -d pulseiq_wh -v ro_password="$PW" -f - < sql/10_readonly_role.sql
-- The role can read ONLY the reporting schema (views without personal data).
SELECT format('CREATE ROLE superset_ro LOGIN PASSWORD %L', :'ro_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'superset_ro') \gexec
SELECT format('ALTER ROLE superset_ro PASSWORD %L', :'ro_password') \gexec

ALTER ROLE superset_ro SET default_transaction_read_only = on;
ALTER ROLE superset_ro SET statement_timeout = '60s';

GRANT USAGE ON SCHEMA reporting TO superset_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA reporting TO superset_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA reporting GRANT SELECT ON TABLES TO superset_ro;

-- Nothing in the warehouse schema, where names and birth dates live.
REVOKE ALL ON ALL TABLES IN SCHEMA dw FROM superset_ro;
REVOKE ALL ON SCHEMA dw FROM superset_ro;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM superset_ro;
REVOKE ALL ON SCHEMA public FROM superset_ro;
