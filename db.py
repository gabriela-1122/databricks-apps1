"""db.py - Databricks SQL connection helpers"""
from databricks import sql
import os
import pandas as pd

DATABRICKS_HOST = os.getenv("DATABRICKS_HOST")
HTTP_PATH = os.getenv("HTTP_PATH")
DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN")

# Fail fast instead of hanging forever if the warehouse is
# slow to respond / unreachable. Tune up if your warehouse
# genuinely needs longer to cold-start.
CONNECT_TIMEOUT_SECONDS = 30


def get_connection():
    if not DATABRICKS_HOST or not HTTP_PATH or not DATABRICKS_TOKEN:
        missing = [
            name for name, val in [
                ("DATABRICKS_HOST", DATABRICKS_HOST),
                ("HTTP_PATH", HTTP_PATH),
                ("DATABRICKS_TOKEN", DATABRICKS_TOKEN),
            ] if not val
        ]
        raise RuntimeError(
            f"Missing required env var(s): {', '.join(missing)}. "
            "Check app.yaml secret mappings."
        )
    return sql.connect(
        server_hostname=DATABRICKS_HOST.replace("https://", ""),
        http_path=HTTP_PATH,
        access_token=DATABRICKS_TOKEN,
        _socket_timeout=CONNECT_TIMEOUT_SECONDS,
    )


def run_query(query: str) -> pd.DataFrame:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
            cols = [d[0].upper() for d in cur.description]
            return pd.DataFrame(rows, columns=cols)


def run_write(query: str) -> None:
    """Execute a write statement (INSERT, UPDATE, DELETE, MERGE) with no return value."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)