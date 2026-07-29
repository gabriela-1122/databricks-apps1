"""db.py - Databricks SQL connection helpers"""

from databricks import sql
from databricks.sdk import WorkspaceClient
import os
import pandas as pd


def get_connection():
    """
    Create a Databricks SQL connection using the App service principal identity.
    """

    w = WorkspaceClient()

    warehouse_id = os.environ["SQL_WAREHOUSE_ID"]

    return sql.connect(
        server_hostname=w.config.host.replace("https://", ""),
        http_path=f"/sql/1.0/warehouses/{warehouse_id}",
        auth_type="databricks-oauth"
    )


def run_query(query: str) -> pd.DataFrame:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
            cols = [d[0].upper() for d in cur.description]
            return pd.DataFrame(rows, columns=cols)


def run_write(query: str) -> None:
    """
    Execute a write statement (INSERT, UPDATE, DELETE, MERGE)
    with no return value.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)