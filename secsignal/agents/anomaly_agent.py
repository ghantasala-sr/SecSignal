"""Anomaly agent — risk flag detection specialist.

Runs z-score anomaly detection, retrieves supporting context from risk
factor filings, and collects relevant chart data.
"""

from __future__ import annotations

import structlog

from secsignal.agents.state import FilingState
from secsignal.agents.tools.anomaly_scorer import detect_anomalies
from secsignal.agents.tools.sql_tool import query_risk_factors
from secsignal.agents.tools.semantic_tool import search_filing_text
from secsignal.agents.tools.visual_tool import search_charts
from secsignal.agents.tools.chart_generator import generate_trend_charts

logger = structlog.get_logger(__name__)


def anomaly_agent(state: FilingState) -> dict:
    """Detect and contextualize anomalies in SEC filings.

    1. Runs z-score anomaly detection over risk factor word count changes
    2. Retrieves risk factor text for flagged filings
    3. Searches for relevant filing context via Cortex Search
    4. Optionally retrieves charts if visual intent detected
    """
    query = state["query"]
    tickers = state.get("tickers", [])
    visual_intent = state.get("visual_intent", False)

    sql_results = []
    retrieved_chunks = []
    retrieved_charts = []
    anomaly_scores = []
    generated_charts = []

    # 1. Run anomaly detection
    if tickers:
        for ticker in tickers:
            try:
                anomalies = detect_anomalies(ticker=ticker)
                for a in anomalies:
                    anomaly_scores.append({
                        "ticker": a["ticker"],
                        "metric": a["metric"],
                        "filing_date": a["filing_date"],
                        "value": a["value"],
                        "z_score": a["z_score"],
                        "direction": a["direction"],
                    })
            except Exception:
                logger.exception("anomaly_detection_failed", ticker=ticker)
    else:
        # Scan all companies
        try:
            anomalies = detect_anomalies(ticker=None)
            for a in anomalies:
                anomaly_scores.append({
                    "ticker": a["ticker"],
                    "metric": a["metric"],
                    "filing_date": a["filing_date"],
                    "value": a["value"],
                    "z_score": a["z_score"],
                    "direction": a["direction"],
                })
        except Exception:
            logger.exception("anomaly_detection_all_failed")

    # 2. Get risk factor details — prioritize flagged tickers, but always
    #    include requested tickers so the synthesizer has data for all companies
    flagged_tickers = list({a["ticker"] for a in anomaly_scores})
    tickers_to_query = flagged_tickers or tickers or []
    if not tickers_to_query:
        # No specific tickers — pull a broad sample
        tickers_to_query = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA"]
    for ticker in tickers_to_query[:6]:
        try:
            risks = query_risk_factors(ticker=ticker, limit=3)
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
            logger.exception("anomaly_risk_factors_failed", ticker=ticker)

    # 3. Semantic search for context — spread across tickers for coverage
    search_query = f"unusual changes risks {query}"
    search_tickers = tickers[:3] if tickers else [None]
    for search_ticker in search_tickers:
        try:
            chunks = search_filing_text(
                query=search_query,
                ticker=search_ticker,
                limit=3 if len(search_tickers) > 1 else 5,
            )
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
            logger.exception("anomaly_semantic_failed", ticker=search_ticker)

    # 4. Visual search if requested
    if visual_intent:
        try:
            vis_ticker = tickers[0] if tickers else None
            charts = search_charts(query=query, ticker=vis_ticker, limit=3)
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
            logger.exception("anomaly_visual_failed")

    # 5. Generate trend charts for flagged/requested tickers
    chart_tickers = flagged_tickers or tickers_to_query[:3]
    for ticker in chart_tickers:
        try:
            trend_charts = generate_trend_charts(ticker=ticker)
            generated_charts.extend(trend_charts)
        except Exception:
            logger.exception("anomaly_trend_chart_failed", ticker=ticker)

    logger.info(
        "anomaly_agent_done",
        tickers=flagged_tickers,
        anomalies=len(anomaly_scores),
        sql_results=len(sql_results),
        chunks=len(retrieved_chunks),
    )

    return {
        "sql_results": sql_results,
        "retrieved_chunks": retrieved_chunks,
        "retrieved_charts": retrieved_charts,
        "anomaly_scores": anomaly_scores,
        "generated_charts": generated_charts,
    }
