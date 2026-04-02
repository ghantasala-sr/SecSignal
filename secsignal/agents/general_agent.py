"""General agent — broad factual lookup for SEC filings.

Handles queries that don't fit neatly into trend/comparison/anomaly
categories. Does broad semantic search across all filings and pulls
structured data from multiple marts without time-series specialization.

This replaces the old behavior where "general" queries were misrouted
to trend_agent (a time-series specialist), causing poor accuracy.
"""

from __future__ import annotations

import structlog

from secsignal.agents.state import FilingState
from secsignal.agents.tools.sql_tool import (
    query_financials,
    query_risk_factors,
    query_extracted_financials,
)
from secsignal.agents.tools.semantic_tool import search_filing_text
# --- Advanced viz imports (removable: advanced-viz) ---
from secsignal.agents.tools.chart_generator import (
    generate_financial_radar,
    generate_expense_pie,
    generate_income_waterfall,
)
# --- End advanced viz imports ---

logger = structlog.get_logger(__name__)


def general_agent(state: FilingState) -> dict:
    """Broad factual lookup across all SEC filings.

    Retrieves:
    1. Semantic search results (broad, no single-ticker bias)
    2. Financial data for mentioned tickers (if any)
    3. Risk factor data for mentioned tickers (if any)
    """
    query = state["query"]
    tickers = state.get("tickers", [])

    sql_results = []
    retrieved_chunks = []
    # --- Advanced viz (removable: advanced-viz) ---
    generated_charts: list = []
    # --- End advanced viz ---

    # 1. Broad semantic search — the primary retrieval for general queries
    #    Search without ticker filter first for breadth, then with ticker if specified
    try:
        chunks = search_filing_text(query=query, ticker=None, limit=8)
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
        logger.exception("general_semantic_search_failed")

    # 2. If specific tickers mentioned, get their structured data
    for ticker in tickers[:3]:  # cap at 3 tickers
        try:
            financials = query_financials(ticker=ticker, limit=10)
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
            logger.exception("general_financials_failed", ticker=ticker)

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
            logger.exception("general_risk_factors_failed", ticker=ticker)

        try:
            extracted = query_extracted_financials(ticker=ticker, limit=10)
            for row in extracted:
                sql_results.append({
                    "source": "extracted_financials",
                    "ticker": row.get("TICKER", ""),
                    "filing_date": str(row.get("FILING_DATE", "")),
                    "metric_name": row.get("METRIC_NAME", ""),
                    "metric_category": row.get("METRIC_CATEGORY", ""),
                    "value": row.get("VALUE", 0),
                    "period": row.get("PERIOD", ""),
                    "unit": row.get("UNIT", ""),
                })
        except Exception:
            logger.exception("general_extracted_failed", ticker=ticker)

    # --- Advanced viz generation (removable: advanced-viz) ---
    # Generate rich charts for the first ticker that has data
    for ticker in tickers[:2]:
        try:
            generated_charts.extend(generate_financial_radar(ticker=ticker))
        except Exception:
            logger.exception("general_radar_failed", ticker=ticker)
        try:
            generated_charts.extend(generate_expense_pie(ticker=ticker))
        except Exception:
            logger.exception("general_pie_failed", ticker=ticker)
        try:
            generated_charts.extend(generate_income_waterfall(ticker=ticker))
        except Exception:
            logger.exception("general_waterfall_failed", ticker=ticker)
    # --- End advanced viz generation ---

    logger.info(
        "general_agent_done",
        tickers=tickers,
        sql_results=len(sql_results),
        chunks=len(retrieved_chunks),
    )

    return {
        "sql_results": sql_results,
        "retrieved_chunks": retrieved_chunks,
        "retrieved_charts": [],
        "generated_charts": generated_charts,
    }
