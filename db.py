"""db.py - Databricks SQL connection helpers"""

from databricks import sql
import os
import pandas as pd


DATABRICKS_HOST = os.getenv("DATABRICKS_HOST")
HTTP_PATH = os.getenv("HTTP_PATH")
DATABRICKS_CLIENT_ID = os.getenv("DATABRICKS_CLIENT_ID")
DATABRICKS_CLIENT_SECRET = os.getenv("DATABRICKS_CLIENT_SECRET")


def get_connection():
    return sql.connect(
        server_hostname=DATABRICKS_HOST.replace("https://", ""),
        http_path=HTTP_PATH,
        auth_type="oauth",
        client_id=DATABRICKS_CLIENT_ID,
        client_secret=DATABRICKS_CLIENT_SECRET,
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