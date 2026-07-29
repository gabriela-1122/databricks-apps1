from databricks import sql
import os
import pandas as pd


def get_connection():
    return sql.connect(
        server_hostname=os.environ["DATABRICKS_HOST"].replace("https://", ""),
        http_path=os.environ["HTTP_PATH"],
        auth_type="oauth"
    )


def run_query(query: str) -> pd.DataFrame:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
            cols = [d[0].upper() for d in cur.description]
            return pd.DataFrame(rows, columns=cols)


def run_write(query: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)