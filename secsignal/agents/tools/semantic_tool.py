"""Semantic search tool — Cortex Search retrieval via SQL.

Uses SNOWFLAKE.CORTEX.SEARCH_PREVIEW() since snowflake.core is not installed.
Searches the FILING_SEARCH_SERVICE over the SEARCH_CORPUS table.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from secsignal.agents.connection import get_snowflake_connection

logger = structlog.get_logger(__name__)

SERVICE_NAME = "SECSIGNAL.RAW.FILING_SEARCH_SERVICE"
SEARCH_COLUMNS = ["CONTENT", "TICKER", "FILING_TYPE", "FILING_DATE", "CONTENT_TYPE", "SECTION_KEY"]


def search_filing_text(
    query: str,
    ticker: str | None = None,
    filing_type: str | None = None,
    content_type: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Search filing text using Cortex Search service.

    Args:
        query: Natural language search query.
        ticker: Filter by company ticker (e.g. 'AAPL'). None for all.
        filing_type: Filter by filing type (e.g. '10-K'). None for all.
        content_type: Filter by content type ('text_chunk' or 'chart_description').
        limit: Max results.

    Returns:
        List of dicts with content, ticker, filing_type, filing_date, score.
    """
    conn = get_snowflake_connection()
    cursor = conn.cursor()
    try:
        search_params: dict[str, Any] = {
            "query": query,
            "columns": SEARCH_COLUMNS,
            "limit": limit,
        }

        # Build filter if any filter criteria provided
        filters: dict[str, Any] = {}
        if ticker:
            filters["@eq"] = {"TICKER": ticker.upper()}
        if filing_type:
            if "@eq" in filters:
                # Cortex Search supports @and for multiple filters
                filters = {
                    "@and": [
                        {"@eq": {"TICKER": ticker.upper()}},
                        {"@eq": {"FILING_TYPE": filing_type}},
                    ]
                }
            else:
                filters["@eq"] = {"FILING_TYPE": filing_type}
        if content_type:
            ct_filter = {"@eq": {"CONTENT_TYPE": content_type}}
            if "@and" in filters:
                filters["@and"].append(ct_filter)
            elif "@eq" in filters:
                filters = {"@and": [{"@eq": filters["@eq"]}, ct_filter]}
            else:
                filters = ct_filter

        if filters:
            search_params["filter"] = filters

        params_json = json.dumps(search_params)

        cursor.execute(
            """
            SELECT PARSE_JSON(
                SNOWFLAKE.CORTEX.SEARCH_PREVIEW(%s, %s)
            ) AS results
            """,
            (SERVICE_NAME, params_json),
        )

        row = cursor.fetchone()
        if not row or not row[0]:
            return []

        response = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        results = response.get("results", [])

        # Normalize results to a clean format
        normalized = []
        for r in results:
            normalized.append({
                "content": r.get("CONTENT", ""),
                "ticker": r.get("TICKER", ""),
                "filing_type": r.get("FILING_TYPE", ""),
                "filing_date": r.get("FILING_DATE", ""),
                "content_type": r.get("CONTENT_TYPE", ""),
                "section_key": r.get("SECTION_KEY", ""),
                "score": r.get("@scores", {}).get("cosine_similarity", 0.0),
            })

        logger.debug(
            "search_filing_text",
            query=query[:50],
            ticker=ticker,
            results=len(normalized),
        )
        return normalized

    except Exception:
        logger.exception("search_filing_text_failed", query=query[:50])
        return []
    finally:
        cursor.close()
