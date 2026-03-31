"""Chart data generator — produces structured data for Streamlit native charts.

Instead of relying on pre-extracted chart images (which are mostly logos),
this tool queries EXTRACTED_FINANCIALS and returns structured data that the
frontend can render using st.bar_chart / st.line_chart / altair.
"""

from __future__ import annotations

from typing import Any

import structlog

from secsignal.agents.connection import get_snowflake_connection

logger = structlog.get_logger(__name__)


def generate_chart_data(
    ticker: str | None = None,
    metric_category: str | None = None,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """Generate chart-ready data from extracted financial metrics.

    Queries EXTRACTED_FINANCIALS and returns structured rows suitable
    for rendering as bar/line charts in Streamlit.

    Args:
        ticker: Filter by ticker. None for all.
        metric_category: Filter by category (e.g. 'revenue', 'income').
        limit: Max data points.

    Returns:
        List of dicts with chart_type, title, data (list of {label, value}).
        Each dict represents one chart to render.
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
            SELECT TICKER, FILING_TYPE, FILING_DATE, METRIC_NAME,
                   METRIC_CATEGORY, VALUE, PERIOD, UNIT
            FROM SECSIGNAL.RAW.EXTRACTED_FINANCIALS
            {where}
            ORDER BY METRIC_CATEGORY, METRIC_NAME, FILING_DATE
            LIMIT %s
        """
        cursor.execute(sql, params)
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        if not rows:
            logger.debug("generate_chart_data_empty", ticker=ticker)
            return []

        # Group by metric_category to produce one chart per category
        charts = _group_into_charts(rows, ticker)
        logger.debug("generate_chart_data", ticker=ticker, charts=len(charts))
        return charts

    except Exception:
        logger.exception("generate_chart_data_failed", ticker=ticker)
        return []
    finally:
        cursor.close()


def _group_into_charts(
    rows: list[dict[str, Any]], ticker: str | None
) -> list[dict[str, Any]]:
    """Group flat metric rows into chart structures."""
    from collections import defaultdict

    by_category: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        cat = r.get("METRIC_CATEGORY", "other")
        by_category[cat].append(r)

    charts = []
    for category, cat_rows in by_category.items():
        if category in ("growth", "other"):
            # Growth metrics work well as bar charts
            chart_type = "bar"
        elif category == "margin":
            chart_type = "bar"
        else:
            # revenue, income, expense, etc. — bar chart for comparison
            chart_type = "bar"

        # Build data points: each row is a data point
        data_points = []
        for r in cat_rows:
            label = r.get("METRIC_NAME", "Unknown")
            period = r.get("PERIOD", "")
            if period:
                label = f"{label} ({period})"
            data_points.append({
                "label": label,
                "value": float(r.get("VALUE", 0)),
                "unit": r.get("UNIT", ""),
                "ticker": r.get("TICKER", ""),
                "period": period,
                "metric_name": r.get("METRIC_NAME", ""),
            })

        ticker_label = ticker.upper() if ticker else "All Companies"
        title = f"{ticker_label} — {category.replace('_', ' ').title()} Metrics"

        # Determine unit for axis label
        units = {dp["unit"] for dp in data_points if dp["unit"]}
        unit_label = units.pop() if len(units) == 1 else "mixed"

        charts.append({
            "chart_type": chart_type,
            "title": title,
            "category": category,
            "unit": unit_label,
            "ticker": ticker or "ALL",
            "data": data_points,
        })

    return charts
