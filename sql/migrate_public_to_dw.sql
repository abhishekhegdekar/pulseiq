-- One-off: move the warehouse tables from schema public to schema dw (Step 95b).
-- Run once on a database that was loaded before Step 95b. A new database does not need it.
CREATE SCHEMA IF NOT EXISTS dw;
DO $$
DECLARE t text;
BEGIN
    FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
        EXECUTE format('ALTER TABLE public.%I SET SCHEMA dw', t);
    END LOOP;
END $$;
DO $$ BEGIN
    EXECUTE format('ALTER DATABASE %I SET search_path = dw, public', current_database());
END $$;
