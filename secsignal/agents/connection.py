"""Shared Snowflake connection factory for agent tools.

Provides a thread-safe singleton connection that is reused across all
tool calls within a session. This avoids the overhead of creating 5-15
new connections per query (one per tool call).

Uses the same connection pattern as run_pipeline.py — env vars for credentials.
"""

from __future__ import annotations

import os
import threading

import snowflake.connector
import structlog

logger = structlog.get_logger(__name__)

_lock = threading.Lock()
_connection: snowflake.connector.SnowflakeConnection | None = None


def get_snowflake_connection() -> snowflake.connector.SnowflakeConnection:
    """Get or create a shared Snowflake connection.

    Thread-safe singleton: the first call creates the connection,
    subsequent calls reuse it. If the connection has gone stale,
    it is automatically recreated.

    Required env vars: SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD,
    SNOWFLAKE_WAREHOUSE, SNOWFLAKE_DATABASE, SNOWFLAKE_ROLE.
    """
    global _connection

    with _lock:
        if _connection is not None:
            try:
                # Quick health check — raises if connection is dead
                _connection.cursor().execute("SELECT 1").close()
                return _connection
            except Exception:
                logger.warning("snowflake_connection_stale, reconnecting")
                try:
                    _connection.close()
                except Exception:
                    pass
                _connection = None

        _connection = snowflake.connector.connect(
            account=os.environ["SNOWFLAKE_ACCOUNT"],
            user=os.environ["SNOWFLAKE_USER"],
            password=os.environ["SNOWFLAKE_PASSWORD"],
            warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
            database=os.environ.get("SNOWFLAKE_DATABASE", "SECSIGNAL"),
            role=os.environ.get("SNOWFLAKE_ROLE", "TRAINING_ROLE"),
        )
        logger.debug("snowflake_connected", account=os.environ["SNOWFLAKE_ACCOUNT"])
        return _connection


def close_connection() -> None:
    """Close the shared connection. Call at app shutdown."""
    global _connection

    with _lock:
        if _connection is not None:
            try:
                _connection.close()
                logger.debug("snowflake_connection_closed")
            except Exception:
                pass
            _connection = None
