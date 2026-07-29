"""db.py - Databricks SQL connection helpers"""
import os
from databricks import sql
import pandas as pd

DATABRICKS_HOST = os.environ["DATABRICKS_HOST"].replace("https://", "").rstrip("/")
HTTP_PATH       = os.environ["HTTP_PATH"]
DATABRICKS_TOKEN = os.environ["DATABRICKS_TOKEN"]


def get_connection():
    return sql.connect(
        server_hostname=DATABRICKS_HOST,
        http_path=HTTP_PATH,
        access_token=DATABRICKS_TOKEN,
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



print("LOADED DB.PY FROM:", __file__)
print("TOKEN PREFIX:", os.environ["DATABRICKS_TOKEN"])