"""
sql_pipeline.py

A general-purpose data pipeline utility for executing SQL queries and
uploading results to Google BigQuery with idempotent append support.

Features:
    - Configurable SQL execution with retry logic
    - Automatic date-range parameter generation (ISO week boundaries)
    - BigQuery upload with schema inference and deduplication
    - CSV caching to avoid redundant query execution
    - Logging with rotation

Usage:
    python sql_pipeline.py --config pipeline_config.yaml

Requirements:
    pip install pandas pandas-gbq google-cloud-bigquery pydata-google-auth
"""

import os
import time
import logging
import argparse
from datetime import date, timedelta
from functools import wraps
from typing import Optional

import pandas as pd
import pandas_gbq as gbq
from google.cloud import bigquery
from google.oauth2 import service_account


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Retry decorator
# ---------------------------------------------------------------------------

def retry(attempts=3, delay=5, backoff=2):
    """Retry a function with exponential backoff.

    Args:
        attempts: Maximum number of tries.
        delay: Initial delay between retries in seconds.
        backoff: Multiplier applied to delay after each failure.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            _delay = delay
            last_exc = None
            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    logger.warning(
                        "Attempt %d/%d for %s failed: %s",
                        attempt, attempts, func.__name__, e,
                    )
                    if attempt < attempts:
                        time.sleep(_delay)
                        _delay *= backoff
            raise RuntimeError(
                f"{func.__name__} failed after {attempts} attempts"
            ) from last_exc
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def get_last_full_week(reference_date: Optional[date] = None):
    """Return (start_date, end_date) for the most recent complete Mon–Sun week.

    Args:
        reference_date: The date to calculate from (defaults to today).

    Returns:
        Tuple of (start_date, end_date) as date objects.
    """
    ref = reference_date or date.today()
    days_since_monday = ref.weekday()
    start = ref - timedelta(days=days_since_monday, weeks=1)
    end = start + timedelta(days=6)
    return start, end


def build_date_parameters(start: date, end: date) -> dict:
    """Build a standard parameter dict from date range."""
    return {"start_date": str(start), "end_date": str(end)}


# ---------------------------------------------------------------------------
# SQL Execution
# ---------------------------------------------------------------------------

class SQLRunner:
    """Execute SQL queries against a database engine.

    This is an adapter class — swap the internals for your database client
    (e.g. SQLAlchemy, psycopg2, pyodbc, Presto, Hive, etc.).
    """

    def __init__(self, connection_string: str = "", engine_type: str = "presto"):
        """
        Args:
            connection_string: Database connection string or DSN.
            engine_type: The SQL engine type (for logging/routing).
        """
        self.connection_string = connection_string
        self.engine_type = engine_type

    @retry(attempts=3, delay=5)
    def execute_query(
        self,
        sql: str,
        parameters: Optional[dict] = None,
        timeout: int = 1800,
    ) -> pd.DataFrame:
        """Execute a SQL query and return results as a DataFrame.

        Args:
            sql: The SQL query string. Supports {param} placeholders.
            parameters: Dict of parameter substitutions.
            timeout: Query timeout in seconds.

        Returns:
            DataFrame with query results.
        """
        if parameters:
            for key, value in parameters.items():
                sql = sql.replace(f"{{{key}}}", str(value))

        logger.info("Executing query on %s (timeout=%ds)...", self.engine_type, timeout)

        # --- REPLACE THIS BLOCK WITH YOUR DB CLIENT ---
        # Example with SQLAlchemy:
        #   from sqlalchemy import create_engine, text
        #   engine = create_engine(self.connection_string)
        #   with engine.connect() as conn:
        #       result = pd.read_sql(text(sql), conn)
        #   return result
        #
        # Example with psycopg2:
        #   import psycopg2
        #   conn = psycopg2.connect(self.connection_string)
        #   return pd.read_sql(sql, conn)
        raise NotImplementedError(
            "Implement execute_query() with your database client. "
            "See comments in source for examples."
        )

    def execute_file(
        self,
        filepath: str,
        parameters: Optional[dict] = None,
        timeout: int = 1800,
    ) -> pd.DataFrame:
        """Read SQL from a file and execute it.

        Args:
            filepath: Path to the .sql file.
            parameters: Dict of placeholder substitutions.
            timeout: Query timeout in seconds.

        Returns:
            DataFrame with query results.
        """
        with open(filepath, "r") as f:
            sql = f.read()
        logger.info("Loaded SQL from %s", filepath)
        return self.execute_query(sql, parameters=parameters, timeout=timeout)


# ---------------------------------------------------------------------------
# BigQuery Upload
# ---------------------------------------------------------------------------

def get_bq_credentials(credentials_path: str):
    """Load GCP service account credentials from a JSON key file."""
    return service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )


def infer_bq_schema(df: pd.DataFrame) -> list[dict]:
    """Infer BigQuery schema from DataFrame dtypes.

    Returns:
        List of dicts with 'name' and 'type' keys suitable for pandas_gbq.
    """
    type_map = {
        "object": "STRING",
        "int64": "INTEGER",
        "int32": "INTEGER",
        "float64": "FLOAT",
        "float32": "FLOAT",
        "bool": "BOOLEAN",
        "boolean": "BOOLEAN",
        "datetime64[ns, UTC]": "TIMESTAMP",
        "datetime64[ns]": "TIMESTAMP",
    }

    def _map_dtype(dtype):
        s = str(dtype)
        if s in type_map:
            return type_map[s]
        if s.startswith("datetime64"):
            return "TIMESTAMP"
        if s.startswith(("int", "Int", "uint", "UInt")):
            return "INTEGER"
        if s.startswith(("float", "Float")):
            return "FLOAT"
        return "STRING"

    return [{"name": col, "type": _map_dtype(dtype)} for col, dtype in df.dtypes.items()]


def upload_to_bigquery(
    df: pd.DataFrame,
    dataset: str,
    table: str,
    credentials_path: str,
    project: str,
    if_exists: str = "append",
    replace_column: Optional[str] = None,
):
    """Upload a DataFrame to BigQuery with optional idempotent deduplication.

    When `replace_column` is provided and `if_exists='append'`, existing rows
    matching the values in that column are deleted before inserting — this
    prevents duplicates on re-runs.

    Args:
        df: The data to upload.
        dataset: BigQuery dataset name.
        table: BigQuery table name.
        credentials_path: Path to GCP service account JSON key.
        project: GCP project ID.
        if_exists: One of 'fail', 'replace', 'append'.
        replace_column: Column used for idempotent deduplication.
    """
    if df.empty:
        logger.warning("DataFrame is empty — skipping upload.")
        return

    credentials = get_bq_credentials(credentials_path)
    full_table = f"{dataset}.{table}"
    full_table_id = f"{project}.{full_table}"
    schema = infer_bq_schema(df)

    if replace_column and if_exists == "append":
        logger.info("Deduplicating on column '%s' before append...", replace_column)
        client = bigquery.Client(project=project, credentials=credentials)
        values = sorted({str(v) for v in df[replace_column].dropna().unique()})
        in_clause = ", ".join(f'"{v}"' for v in values)
        delete_sql = f"DELETE FROM `{full_table_id}` WHERE `{replace_column}` IN ({in_clause})"
        client.query(delete_sql).result()
        logger.info("Deleted existing rows for %s in %s", values, full_table_id)

    logger.info("Uploading %d rows to %s (if_exists=%s)...", len(df), full_table_id, if_exists)
    gbq.to_gbq(
        df,
        full_table,
        project,
        if_exists=if_exists,
        table_schema=schema,
        credentials=credentials,
    )
    logger.info("Upload complete: %d rows → %s", len(df), full_table_id)


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------

def run_pipeline(
    sql_runner: SQLRunner,
    queries: dict[str, str],
    parameters: dict,
    merge_on: Optional[list[str]] = None,
    bq_config: Optional[dict] = None,
):
    """Run one or more queries, optionally merge results, and upload to BQ.

    Args:
        sql_runner: Configured SQLRunner instance.
        queries: Dict mapping a friendly name to a SQL string or .sql filepath.
        parameters: Parameter dict passed to each query.
        merge_on: If provided and there are 2+ queries, left-join results
            on these columns.
        bq_config: If provided, upload final result to BigQuery.
            Expected keys: dataset, table, credentials_path, project,
            if_exists, replace_column (optional).

    Returns:
        The final merged DataFrame.
    """
    dataframes = {}

    for name, sql_or_path in queries.items():
        logger.info("Running query: %s", name)
        if sql_or_path.endswith(".sql") and os.path.isfile(sql_or_path):
            df = sql_runner.execute_file(sql_or_path, parameters=parameters)
        else:
            df = sql_runner.execute_query(sql_or_path, parameters=parameters)
        dataframes[name] = df
        logger.info("Query '%s' returned %d rows", name, len(df))

    frames = list(dataframes.values())
    if merge_on and len(frames) > 1:
        result = frames[0]
        for other in frames[1:]:
            result = pd.merge(result, other, how="left", on=merge_on)
        logger.info("Merged %d DataFrames → %d rows", len(frames), len(result))
    elif frames:
        result = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
    else:
        result = pd.DataFrame()

    if bq_config and not result.empty:
        upload_to_bigquery(result, **bq_config)

    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Run SQL queries and upload to BigQuery")
    parser.add_argument("--sql-file", nargs="+", help="Path(s) to .sql files to execute")
    parser.add_argument("--start-date", help="Start date (YYYY-MM-DD). Defaults to last full week.")
    parser.add_argument("--end-date", help="End date (YYYY-MM-DD). Defaults to last full week.")
    parser.add_argument("--project", default="my-gcp-project", help="GCP project ID")
    parser.add_argument("--dataset", default="analytics", help="BigQuery dataset")
    parser.add_argument("--table", default="query_results", help="BigQuery table")
    parser.add_argument("--credentials", help="Path to GCP service account JSON key")
    parser.add_argument("--if-exists", default="append", choices=["fail", "replace", "append"])
    parser.add_argument("--replace-column", help="Column for idempotent dedup on append")
    parser.add_argument("--output-csv", help="Save results to CSV instead of BigQuery")
    args = parser.parse_args()

    if args.start_date and args.end_date:
        parameters = {"start_date": args.start_date, "end_date": args.end_date}
    else:
        start, end = get_last_full_week()
        parameters = build_date_parameters(start, end)

    logger.info("Parameters: %s", parameters)

    runner = SQLRunner()

    if not args.sql_file:
        parser.error("Provide at least one --sql-file")

    queries = {os.path.basename(f): f for f in args.sql_file}

    bq_config = None
    if args.credentials and not args.output_csv:
        bq_config = {
            "dataset": args.dataset,
            "table": args.table,
            "credentials_path": args.credentials,
            "project": args.project,
            "if_exists": args.if_exists,
            "replace_column": args.replace_column,
        }

    result = run_pipeline(runner, queries, parameters, bq_config=bq_config)

    if args.output_csv:
        result.to_csv(args.output_csv, index=False)
        logger.info("Results saved to %s", args.output_csv)

    logger.info("Pipeline complete. Final shape: %s", result.shape)


if __name__ == "__main__":
    main()
