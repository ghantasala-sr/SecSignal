"""SQL tool — parameterized queries against dbt mart tables.

Provides structured data retrieval from:
- fct_financials: Filing section word counts by ticker/date
- fct_risk_factors: Risk factor text with change detection
- fct_chart_data: Extracted chart metadata and data points
"""

from __future__ import annotations

from typing import Any

import structlog

from secsignal.agents.connection import get_snowflake_connection

logger = structlog.get_logger(__name__)


def query_financials(
    ticker: str | None = None,
    filing_type: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Query fct_financials for filing section data.

    Args:
        ticker: Filter by company ticker (e.g. 'AAPL'). None for all.
        filing_type: Filter by filing type (e.g. '10-K', '10-Q'). None for all.
        limit: Max rows to return.

    Returns:
        List of dicts with filing financial data.
    """
    conn = get_snowflake_connection()
    cursor = conn.cursor()
    try:
        conditions: list[str] = []
        params: list[Any] = []

        if ticker:
            conditions.append("TICKER = %s")
            params.append(ticker.upper())
        if filing_type:
            conditions.append("FILING_TYPE = %s")
            params.append(filing_type)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        sql = f"""
            SELECT FILING_ID, TICKER, COMPANY_NAME, FILING_TYPE, FILING_DATE,
                   FISCAL_QUARTER, SECTION_KEY, SECTION_TITLE, WORD_COUNT
            FROM SECSIGNAL.MARTS.FCT_FINANCIALS
            {where}
            ORDER BY FILING_DATE DESC
            LIMIT %s
        """
        cursor.execute(sql, params)
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        logger.debug("query_financials", ticker=ticker, rows=len(rows))
        return rows
    finally:
        cursor.close()


def query_risk_factors(
    ticker: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Query fct_risk_factors for risk factor text with change detection.

    Args:
        ticker: Filter by ticker. None for all.
        limit: Max rows.

    Returns:
        List of dicts with risk factor data including word count deltas.
    """
    conn = get_snowflake_connection()
    cursor = conn.cursor()
    try:
        conditions: list[str] = []
        params: list[Any] = []

        if ticker:
            conditions.append("TICKER = %s")
            params.append(ticker.upper())

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        sql = f"""
            SELECT RISK_FACTOR_ID, FILING_ID, TICKER, COMPANY_NAME,
                   FILING_TYPE, FILING_DATE, FISCAL_QUARTER, SECTION_TITLE,
                   WORD_COUNT, PREV_WORD_COUNT, WORD_COUNT_DELTA
            FROM SECSIGNAL.MARTS.FCT_RISK_FACTORS
            {where}
            ORDER BY FILING_DATE DESC
            LIMIT %s
        """
        cursor.execute(sql, params)
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        logger.debug("query_risk_factors", ticker=ticker, rows=len(rows))
        return rows
    finally:
        cursor.close()


def query_extracted_financials(
    ticker: str | None = None,
    metric_category: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Query extracted financial metrics from MD&A sections.

    Returns real financial numbers (revenue, margins, etc.) extracted
    from filing text via Cortex COMPLETE.

    Args:
        ticker: Filter by ticker. None for all.
        metric_category: Filter by category (revenue, income, margin, etc.).
        limit: Max rows.

    Returns:
        List of dicts with metric_name, value, period, unit, etc.
    """
    conn = get_snowflake_connection()
    cursor = conn.cursor()
    try:
        conditions: list[str] = []
        params: list[Any] = []

        if ticker:
            conditions.append("TICKER = %s")
            params.append(ticker.upper())
        if metric_category:
            conditions.append("METRIC_CATEGORY = %s")
            params.append(metric_category.lower())

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        sql = f"""
            SELECT EXTRACT_ID, FILING_ID, TICKER, FILING_TYPE, FILING_DATE,
                   METRIC_NAME, METRIC_CATEGORY, VALUE, PERIOD, UNIT
            FROM SECSIGNAL.RAW.EXTRACTED_FINANCIALS
            {where}
            ORDER BY FILING_DATE DESC, METRIC_CATEGORY, METRIC_NAME
            LIMIT %s
        """
        cursor.execute(sql, params)
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        logger.debug("query_extracted_financials", ticker=ticker, rows=len(rows))
        return rows
    finally:
        cursor.close()


def query_chart_data(
    ticker: str | None = None,
    chart_type: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Query fct_chart_data for extracted chart metadata.

    Args:
        ticker: Filter by ticker. None for all.
        chart_type: Filter by chart type (e.g. 'bar', 'line', 'pie'). None for all.
        limit: Max rows.

    Returns:
        List of dicts with chart extraction data.
    """
    conn = get_snowflake_connection()
    cursor = conn.cursor()
    try:
        conditions: list[str] = []
        params: list[Any] = []

        if ticker:
            conditions.append("TICKER = %s")
            params.append(ticker.upper())
        if chart_type:
            conditions.append("CHART_TYPE = %s")
            params.append(chart_type)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        sql = f"""
            SELECT EXTRACT_ID, IMAGE_ID, FILING_ID, TICKER, COMPANY_NAME,
                   FILING_TYPE, FILING_DATE, FISCAL_QUARTER, CHART_TYPE,
                   CHART_TITLE, EXTRACTED_DATA, DATA_POINTS,
                   CONFIDENCE_SCORE, IMAGE_DESCRIPTION, PAGE_NUMBER
            FROM SECSIGNAL.MARTS.FCT_CHART_DATA
            {where}
            ORDER BY FILING_DATE DESC
            LIMIT %s
        """
        cursor.execute(sql, params)
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        logger.debug("query_chart_data", ticker=ticker, rows=len(rows))
        return rows
    finally:
        cursor.close()
