"""Trend agent — time-series specialist for single-company analysis.

Retrieves financial data over time, filing text context, and optionally
chart images when visual intent is detected.
"""

from __future__ import annotations

import structlog

from secsignal.agents.state import FilingState
from secsignal.agents.tools.sql_tool import query_financials, query_risk_factors, query_extracted_financials
from secsignal.agents.tools.semantic_tool import search_filing_text
from secsignal.agents.tools.visual_tool import search_charts
from secsignal.agents.tools.chart_generator import generate_chart_data, generate_trend_charts
# --- Advanced viz imports (removable: advanced-viz) ---
from secsignal.agents.tools.chart_generator import (
    generate_composed_revenue_margin,
    generate_area_trend,
    generate_expense_pie,
    generate_financial_radar,
    generate_income_waterfall,
)
# --- End advanced viz imports ---

logger = structlog.get_logger(__name__)


def trend_agent(state: FilingState) -> dict:
    """Analyze trends for a single company over time.

    Retrieves:
    1. Financial section data from fct_financials
    2. Risk factor data with change detection from fct_risk_factors
    3. Relevant filing text from Cortex Search
    4. Chart images if visual intent detected
    """
    query = state["query"]
    tickers = state.get("tickers", [])
    visual_intent = state.get("visual_intent", False)

    # Default to first ticker, or None for all
    ticker = tickers[0] if tickers else None

    sql_results = []
    retrieved_chunks = []
    retrieved_charts = []
    generated_charts = []

    # 1. Get financial data
    try:
        financials = query_financials(ticker=ticker, limit=20)
        for row in financials:
            sql_results.append({
                "source": "fct_financials",
                "ticker": row.get("TICKER", ""),
                "filing_date": str(row.get("FILING_DATE", "")),
                "section_key": row.get("SECTION_KEY", ""),
                "word_count": row.get("WORD_COUNT", 0),
                "company_name": row.get("COMPANY_NAME", ""),
            })
    except Exception:
        logger.exception("trend_financials_failed", ticker=ticker)

    # 1b. Get extracted financial metrics (real numbers)
    try:
        extracted = query_extracted_financials(ticker=ticker, limit=30)
        for row in extracted:
            sql_results.append({
                "source": "extracted_financials",
                "ticker": row.get("TICKER", ""),
                "filing_date": str(row.get("FILING_DATE", "")),
                "filing_type": row.get("FILING_TYPE", ""),
                "metric_name": row.get("METRIC_NAME", ""),
                "metric_category": row.get("METRIC_CATEGORY", ""),
                "value": row.get("VALUE", 0),
                "period": row.get("PERIOD", ""),
                "unit": row.get("UNIT", ""),
            })
    except Exception:
        logger.exception("trend_extracted_financials_failed", ticker=ticker)

    # 2. Get risk factor changes
    try:
        risks = query_risk_factors(ticker=ticker, limit=10)
        for row in risks:
            sql_results.append({
                "source": "fct_risk_factors",
                "ticker": row.get("TICKER", ""),
                "filing_date": str(row.get("FILING_DATE", "")),
                "word_count": row.get("WORD_COUNT", 0),
                "word_count_delta": row.get("WORD_COUNT_DELTA", 0),
                "company_name": row.get("COMPANY_NAME", ""),
            })
    except Exception:
        logger.exception("trend_risk_factors_failed", ticker=ticker)

    # 3. Semantic search for relevant text
    try:
        chunks = search_filing_text(query=query, ticker=ticker, limit=5)
        for chunk in chunks:
            retrieved_chunks.append({
                "content": chunk["content"],
                "ticker": chunk["ticker"],
                "filing_type": chunk["filing_type"],
                "filing_date": chunk["filing_date"],
                "content_type": chunk["content_type"],
                "score": chunk["score"],
            })
    except Exception:
        logger.exception("trend_semantic_search_failed", ticker=ticker)

    # 4. Visual search if chart/graph intent detected
    if visual_intent:
        try:
            charts = search_charts(query=query, ticker=ticker, limit=3)
            for chart in charts:
                retrieved_charts.append({
                    "image_id": chart.get("IMAGE_ID", ""),
                    "description": chart.get("DESCRIPTION", ""),
                    "ticker": chart.get("TICKER", ""),
                    "filing_type": chart.get("FILING_TYPE", ""),
                    "filing_date": str(chart.get("FILING_DATE", "")),
                    "chart_type": chart.get("CHART_TYPE", ""),
                    "image_data_b64": chart.get("IMAGE_DATA_B64", ""),
                    "score": float(chart.get("SIMILARITY", 0)),
                    "_warning": chart.get("_warning", ""),
                })
        except Exception:
            logger.exception("trend_visual_search_failed", ticker=ticker)

    # 5. Generate chart data from extracted financials
    try:
        chart_data = generate_chart_data(ticker=ticker)
        generated_charts.extend(chart_data)
    except Exception:
        logger.exception("trend_chart_generation_failed", ticker=ticker)

    # 5b. Generate trend line charts from risk factor time-series
    try:
        trend_charts = generate_trend_charts(ticker=ticker)
        generated_charts.extend(trend_charts)
    except Exception:
        logger.exception("trend_line_chart_failed", ticker=ticker)

    # --- Advanced viz generation (removable: advanced-viz) ---
    if ticker:
        # Composed bar+line: revenue vs margin in one chart
        try:
            generated_charts.extend(generate_composed_revenue_margin(ticker=ticker))
        except Exception:
            logger.exception("trend_composed_failed", ticker=ticker)
        # Area chart: risk disclosure volume with avg reference line
        try:
            generated_charts.extend(generate_area_trend(ticker=ticker))
        except Exception:
            logger.exception("trend_area_failed", ticker=ticker)
        # Pie chart: expense breakdown
        try:
            generated_charts.extend(generate_expense_pie(ticker=ticker))
        except Exception:
            logger.exception("trend_pie_failed", ticker=ticker)
        # Radar chart: financial health profile
        try:
            generated_charts.extend(generate_financial_radar(ticker=ticker))
        except Exception:
            logger.exception("trend_radar_failed", ticker=ticker)
        # Waterfall: income statement flow
        try:
            generated_charts.extend(generate_income_waterfall(ticker=ticker))
        except Exception:
            logger.exception("trend_waterfall_failed", ticker=ticker)
    # --- End advanced viz generation ---

    logger.info(
        "trend_agent_done",
        ticker=ticker,
        sql_results=len(sql_results),
        chunks=len(retrieved_chunks),
        charts=len(retrieved_charts),
        generated_charts=len(generated_charts),
    )

    return {
        "sql_results": sql_results,
        "retrieved_chunks": retrieved_chunks,
        "retrieved_charts": retrieved_charts,
        "generated_charts": generated_charts,
    }
