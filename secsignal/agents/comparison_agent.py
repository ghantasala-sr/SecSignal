"""Comparison agent — multi-company diff specialist.

Retrieves data across multiple tickers and structures comparative results
for side-by-side analysis.
"""

from __future__ import annotations

import structlog

from secsignal.agents.state import FilingState
from secsignal.agents.tools.sql_tool import (
    query_financials,
    query_risk_factors,
    query_chart_data,
    query_extracted_financials,
)
from secsignal.agents.tools.semantic_tool import search_filing_text
from secsignal.agents.tools.visual_tool import search_charts
from secsignal.agents.tools.chart_generator import generate_chart_data, generate_comparison_chart, generate_trend_charts

logger = structlog.get_logger(__name__)


def comparison_agent(state: FilingState) -> dict:
    """Compare data across multiple companies.

    Retrieves financial and risk factor data for each ticker,
    plus relevant filing text and charts for comparison.
    """
    query = state["query"]
    tickers = state.get("tickers", [])
    visual_intent = state.get("visual_intent", False)

    if not tickers:
        # If no tickers extracted, search broadly
        tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]

    sql_results = []
    retrieved_chunks = []
    retrieved_charts = []
    generated_charts = []

    # 1. Get financial data for each ticker
    for ticker in tickers:
        try:
            financials = query_financials(ticker=ticker, limit=5)
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
            logger.exception("comparison_financials_failed", ticker=ticker)

    # 1b. Get extracted financial metrics for each ticker
    for ticker in tickers:
        try:
            extracted = query_extracted_financials(ticker=ticker, limit=15)
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
            logger.exception("comparison_extracted_failed", ticker=ticker)

    # 2. Get risk factor data for each ticker
    for ticker in tickers:
        try:
            risks = query_risk_factors(ticker=ticker, limit=5)
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
            logger.exception("comparison_risk_factors_failed", ticker=ticker)

    # 3. Semantic search — one query per ticker for targeted context
    for ticker in tickers[:3]:  # Limit to 3 to avoid excessive queries
        try:
            chunks = search_filing_text(query=query, ticker=ticker, limit=3)
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
            logger.exception("comparison_semantic_failed", ticker=ticker)

    # 4. Visual search if requested
    if visual_intent:
        for ticker in tickers[:2]:
            try:
                charts = search_charts(query=query, ticker=ticker, limit=2)
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
                logger.exception("comparison_visual_failed", ticker=ticker)

    # 5. Generate chart data from extracted financials for each ticker
    for ticker in tickers[:3]:
        try:
            chart_data = generate_chart_data(ticker=ticker)
            generated_charts.extend(chart_data)
        except Exception:
            logger.exception("comparison_chart_gen_failed", ticker=ticker)

    # 5b. Generate comparison chart across all tickers
    try:
        comp_charts = generate_comparison_chart(tickers=tickers)
        generated_charts.extend(comp_charts)
    except Exception:
        logger.exception("comparison_chart_comparison_failed")

    # 5c. Generate trend line charts for tickers with multiple filings
    for ticker in tickers[:3]:
        try:
            trend_charts = generate_trend_charts(ticker=ticker)
            generated_charts.extend(trend_charts)
        except Exception:
            logger.exception("comparison_trend_chart_failed", ticker=ticker)

    logger.info(
        "comparison_agent_done",
        tickers=tickers,
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
