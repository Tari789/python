"""
query_waiter.py

General-purpose utility for running SQL queries via Querybuilder / Queryrunner.

Supports three execution modes:
    - By report ID   (run_query_id)
    - By run ID      (run_query_run)
    - From raw SQL   (query_from_text)

Includes retry logic, concurrent execution, optional CSV caching, and Slack
notifications.

Usage:
    from query_waiter import Queryrun, run_queries_concurrently

    qr = Queryrun(user_email='you@uber.com', consumer_name='your-consumer')

    # Single report
    df = qr.run_query_id(report_id='abc123', parameters={'date': '2026-01-01'})

    # Raw SQL
    df = qr.query_from_text(engine='presto', query_text='SELECT 1',
                            datacenter='phx2')

    # Concurrent reports
    queries = [
        {'report_id': 'abc123', 'datacenter': 'phx2'},
        {'report_id': 'def456', 'datacenter': 'dca1'},
    ]
    results = run_queries_concurrently(qr, queries, max_workers=5)

    # From a DataFrame of queries
    import pandas as pd
    query_df = pd.DataFrame({
        'query_report_id': ['abc123', 'def456'],
        'datacenter': ['phx2', 'dca1'],
    })
    results = run_queries_concurrently(qr, query_df)
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from functools import wraps
import time
import traceback

import pandas as pd
from queryrunner_client import Client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def retry(retries=5, delay=1):
    """Decorator that retries the wrapped function on any exception.

    Args:
        retries: Maximum number of retry attempts.
        delay: Seconds to sleep between attempts.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            last_exception = None
            for attempt in range(1, retries + 1):
                try:
                    return func(self, *args, **kwargs)
                except Exception as e:
                    last_exception = e
                    logger.warning(
                        "Attempt %d/%d for %s failed: %s",
                        attempt, retries, func.__name__, e,
                    )
                    time.sleep(delay)
            raise RuntimeError(
                f"{func.__name__} failed after {retries} attempts: {last_exception}"
            ) from last_exception
        return wrapper
    return decorator


def run_queries_concurrently(q_wait, queries, max_workers=10):
    """Run queries concurrently via *q_wait.run_query_id*.

    Args:
        q_wait: A :class:`Queryrun` instance.
        queries: A ``list[dict]`` or a :class:`~pandas.DataFrame`.
            Each dict / row must contain *report_id* (or *query_report_id*
            for DataFrames).  Optional keys: *datacenter*, *timeout*,
            *attempts*, *csv_name*, *parameters*.
        max_workers: Thread-pool size.

    Returns:
        ``dict[str, pd.DataFrame]`` mapping each *report_id* to its result.
    """
    if isinstance(queries, pd.DataFrame):
        if "query_report_id" not in queries.columns:
            raise ValueError(
                "DataFrame must contain a 'query_report_id' column."
            )
        defaults = {
            "datacenter": "phx2",
            "timeout": 1800,
            "attempts": 2,
            "csv_name": "",
        }
        query_dicts = []
        for _, row in queries.iterrows():
            query_dicts.append({
                "report_id": row["query_report_id"],
                "datacenter": row.get("datacenter", defaults["datacenter"]),
                "timeout": row.get("timeout", defaults["timeout"]),
                "attempts": row.get("attempts", defaults["attempts"]),
                "csv_name": row.get("csv_name", defaults["csv_name"]),
            })
    elif isinstance(queries, list) and all(isinstance(q, dict) for q in queries):
        query_dicts = queries
    else:
        raise TypeError(
            "queries must be a list of dicts or a pandas DataFrame."
        )

    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_query = {
            executor.submit(q_wait.run_query_id, **q): q
            for q in query_dicts
        }
        for future in as_completed(future_to_query):
            query = future_to_query[future]
            try:
                results[query["report_id"]] = future.result()
            except Exception as e:
                logger.error(
                    "%s generated an exception: %s\n%s",
                    query["report_id"], e, traceback.format_exc(),
                )
    return results


# ---------------------------------------------------------------------------
# Core class
# ---------------------------------------------------------------------------

class Queryrun:
    """General-purpose wrapper around :class:`queryrunner_client.Client`.

    Args:
        user_email: Uber LDAP e-mail used for authentication.
        consumer_name: Optional consumer identifier passed to Queryrunner.
        slack: Optional Slack helper with a ``send_message(message=...)``
            method for notifications.
    """

    def __init__(self, user_email, consumer_name="", slack=None):
        self.slack = slack
        self.qr = Client(user_email=user_email, consumer_name=consumer_name)

    # ---- helpers --------------------------------------------------------

    def _try_read_csv(self, csv_name, label="query"):
        """Return a DataFrame from *csv_name* if the file exists, else None."""
        if not csv_name:
            return None
        try:
            df = pd.read_csv(csv_name)
            logger.info("Loaded cached CSV for %s: %s", label, csv_name)
            return df
        except FileNotFoundError:
            logger.debug("CSV %s not found, will run query", csv_name)
        except Exception as e:
            logger.warning("Could not read CSV %s: %s — running query", csv_name, e)
        return None

    def _save_csv(self, df, csv_name, label="query"):
        """Persist *df* to *csv_name* if the frame is non-empty."""
        if not df.empty and csv_name:
            df.to_csv(csv_name, index=False)
            logger.info("Saved %s results to %s", label, csv_name)

    def _notify(self, message):
        if self.slack:
            self.slack.send_message(message=message)

    # ---- public API -----------------------------------------------------

    @retry(retries=3, delay=1)
    def run_query_id(
        self,
        report_id,
        parameters=None,
        datacenter="phx2",
        timeout=1800,
        attempts=4,
        csv_name="",
        channel=None,
    ):
        """Execute a Querybuilder report by its report ID.

        Args:
            report_id: The Querybuilder report ID.
            parameters: Parameter dict forwarded to the report template.
            datacenter: Target datacenter (default ``'phx2'``).
            timeout: Query timeout in seconds.
            attempts: Internal retry count *inside* this method (the
                ``@retry`` decorator adds another layer).
            csv_name: If given, results are cached to / read from this CSV.
            channel: Unused — kept for backward compatibility.

        Returns:
            :class:`~pandas.DataFrame` with the query results (empty on failure).
        """
        parameters = parameters or {}
        label = f"report:{report_id}"

        cached = self._try_read_csv(csv_name, label)
        if cached is not None:
            self._notify(f"Query {report_id} — loaded {len(cached)} rows from CSV.")
            return cached

        result = pd.DataFrame()
        current_attempt = 1

        while current_attempt <= attempts and result.empty:
            try:
                raw = self.qr.execute_report(
                    report_id,
                    parameters=parameters,
                    datacenter=datacenter,
                    timeout=timeout,
                )
                result = raw.to_pandas()
                logger.info("Query %s succeeded (%d rows)", label, len(result))
                self._notify(f"Query {report_id} executed — {len(result)} rows.")
            except Exception as e:
                logger.error(
                    "Attempt %d/%d for %s failed: %s\n%s",
                    current_attempt, attempts, label, e, traceback.format_exc(),
                )
                self._notify(f"Query {report_id} attempt {current_attempt} failed: {e}")
            finally:
                current_attempt += 1

        self._save_csv(result, csv_name, label)
        return result

    @retry(retries=3, delay=1)
    def run_query_run(
        self,
        run_id,
        parameters=None,
        datacenter="phx2",
        timeout=1800,
        attempts=4,
        csv_name="",
    ):
        """Execute a query by its run ID.

        Args:
            run_id: The Queryrunner run ID.
            parameters: Parameter dict forwarded to the query.
            datacenter: Target datacenter (default ``'phx2'``).
            timeout: Query timeout in seconds.
            attempts: Internal retry count.
            csv_name: Optional CSV cache path.

        Returns:
            :class:`~pandas.DataFrame` with the query results (empty on failure).
        """
        parameters = parameters or {}
        label = f"run:{run_id}"

        cached = self._try_read_csv(csv_name, label)
        if cached is not None:
            return cached

        result = pd.DataFrame()
        current_attempt = 1

        while current_attempt <= attempts and result.empty:
            try:
                raw = self.qr.execute_run(
                    run_id,
                    parameters=parameters,
                    datacenter=datacenter,
                    timeout=timeout,
                )
                result = pd.DataFrame(raw.fetchall(), columns=raw.columns)
                logger.info("Query %s succeeded (%d rows)", label, len(result))
            except Exception as e:
                logger.error(
                    "Attempt %d/%d for %s failed: %s\n%s",
                    current_attempt, attempts, label, e, traceback.format_exc(),
                )
            finally:
                current_attempt += 1

        self._save_csv(result, csv_name, label)
        return result

    @retry(retries=3, delay=1)
    def query_from_text(
        self,
        engine,
        query_text,
        datacenter,
        attempts=4,
        query_name="",
        csv_name="",
    ):
        """Execute raw SQL text.

        Args:
            engine: Execution engine (e.g. ``'presto'``, ``'hive'``,
                ``'warehouse'``).
            query_text: The SQL string to execute.
            datacenter: Target datacenter.
            attempts: Internal retry count.
            query_name: Friendly label used in log messages.
            csv_name: Optional CSV cache path.

        Returns:
            :class:`~pandas.DataFrame` with the query results (empty on failure).
        """
        label = query_name or "unnamed_query"

        cached = self._try_read_csv(csv_name, label)
        if cached is not None:
            return cached

        result = pd.DataFrame()
        current_attempt = 1

        while current_attempt <= attempts and result.empty:
            try:
                raw = self.qr.execute(engine, query_text, datacenter)
                result = pd.DataFrame(raw.load_data())
                logger.info("Query '%s' succeeded (%d rows)", label, len(result))
            except Exception as e:
                logger.error(
                    "Attempt %d/%d for '%s' failed: %s\n%s",
                    current_attempt, attempts, label, e, traceback.format_exc(),
                )
            finally:
                current_attempt += 1

        self._save_csv(result, csv_name, label)
        return result

    def run_sql_file(
        self,
        filepath,
        engine="presto",
        datacenter="phx2",
        parameters=None,
        attempts=4,
        query_name="",
        csv_name="",
    ):
        """Read SQL from a file and execute it via :meth:`query_from_text`.

        Simple ``{{key}}`` placeholders in the SQL text are replaced with
        values from *parameters* before execution.

        Args:
            filepath: Path to the ``.sql`` file.
            engine: Execution engine.
            datacenter: Target datacenter.
            parameters: ``dict`` of placeholder replacements applied to the
                raw SQL text.
            attempts: Internal retry count.
            query_name: Friendly label (defaults to the filename).
            csv_name: Optional CSV cache path.

        Returns:
            :class:`~pandas.DataFrame` with the query results (empty on failure).
        """
        with open(filepath, "r") as f:
            sql = f.read()

        if parameters:
            for key, value in parameters.items():
                sql = sql.replace(f"{{{{{key}}}}}", str(value))

        label = query_name or filepath
        return self.query_from_text(
            engine=engine,
            query_text=sql,
            datacenter=datacenter,
            attempts=attempts,
            query_name=label,
            csv_name=csv_name,
        )
