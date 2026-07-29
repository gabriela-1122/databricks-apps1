"""db.py - Databricks SQL connection helpers"""
from databricks import sql

from pyspark.dbutils import DBUtils
from pyspark.sql import SparkSession

import pandas as pd

spark = SparkSession.builder.getOrCreate()
dbutils = DBUtils(spark)

DATABRICKS_HOST = dbutils.secrets.get(
    scope="dq-app-secrets",
    key="DATABRICKS_HOST"
)

HTTP_PATH = dbutils.secrets.get(
    scope="dq-app-secrets",
    key="HTTP_PATH"
)

DATABRICKS_TOKEN = dbutils.secrets.get(
    scope="dq-app-secrets",
    key="DATABRICKS_TOKEN"
)


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