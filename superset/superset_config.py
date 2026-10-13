"""Superset settings for local use (loaded via SUPERSET_CONFIG_PATH).

Secrets come from environment variables (.env), never from this file.
Lean on purpose: no Redis, no Celery workers, to fit in the 3 GB Docker allowance.
"""
import os

SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]

# Superset's own metadata (users, charts, dashboards) lives in the 'superset' database
# of the same PostgreSQL server. The warehouse data is in the 'pulseiq' database.
SQLALCHEMY_DATABASE_URI = "postgresql+psycopg2://{user}:{password}@db:5432/superset".format(
    user=os.environ["POSTGRES_USER"], password=os.environ["POSTGRES_PASSWORD"])

# In-process cache is enough for one user on a laptop.
CACHE_CONFIG = {"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 300}
DATA_CACHE_CONFIG = CACHE_CONFIG

# The page is only reachable from this computer over plain HTTP (127.0.0.1:8088).
TALISMAN_ENABLED = False
