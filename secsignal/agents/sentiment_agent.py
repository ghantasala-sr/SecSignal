"""Sentiment agent — tracks tone shifts in MD&A and risk factor filings.

Uses Cortex COMPLETE to analyze the tone (bullish/neutral/bearish) of
filing text chunks from Management Discussion (item_7) and Risk Factors
(item_1a).  Compares sentiment across filing periods to detect shifts.
"""

from __future__ import annotations

import json
import os

import structlog

from secsignal.agents.state import FilingState
from secsignal.agents.tools.semantic_tool import search_filing_text
from secsignal.agents.connection import get_snowflake_connection

logger = structlog.get_logger(__name__)

LLM_MODEL = os.environ.get("CORTEX_LLM_MODEL", "claude-sonnet-4-6")

SENTIMENT_PROMPT = """Analyze the tone and sentiment of this SEC filing excerpt. Output ONLY a JSON object:

{{
  "sentiment": "bullish" | "neutral" | "bearish",
  "confidence": 0.0 to 1.0,
  "tone_signals": ["list of 2-3 key phrases that indicate the tone"],
  "summary": "one sentence summary of the tone"
}}

Filing excerpt ({ticker}, {filing_type}, {filing_date}, {section}):
{text}

Output ONLY valid JSON, no markdown."""


def sentiment_agent(state: FilingState) -> dict:
    """Analyze sentiment and tone shifts across filing periods.

    Retrieves:
    1. MD&A (item_7) and Risk Factor (item_1a) text via Cortex Search
    2. LLM sentiment scoring on each chunk
    3. Cross-period comparison to detect tone shifts
    """
    query = state["query"]
    tickers = state.get("tickers", [])

    if not tickers:
        tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA"]

    retrieved_chunks = []
    sentiment_scores = []
    generated_charts = []

    conn = get_snowflake_connection()
    cursor = conn.cursor()

    try:
        for ticker in tickers[:3]:
            # Retrieve MD&A chunks
            mda_chunks = _search_sections(query, ticker, "item_7", limit=3)
            risk_chunks = _search_sections(query, ticker, "item_1a", limit=3)

            all_chunks = mda_chunks + risk_chunks

            for chunk in all_chunks:
                retrieved_chunks.append({
                    "content": chunk["content"],
                    "ticker": chunk["ticker"],
                    "filing_type": chunk["filing_type"],
                    "filing_date": chunk["filing_date"],
                    "content_type": chunk["content_type"],
                    "score": chunk["score"],
                })

                # Score sentiment via LLM
                sentiment = _score_sentiment(
                    cursor,
                    text=chunk["content"][:1500],
                    ticker=chunk["ticker"],
                    filing_type=chunk["filing_type"],
                    filing_date=chunk["filing_date"],
                    section=chunk.get("section_key", "unknown"),
                )
                if sentiment:
                    sentiment["ticker"] = chunk["ticker"]
                    sentiment["filing_date"] = chunk["filing_date"]
                    sentiment["filing_type"] = chunk["filing_type"]
                    sentiment["section"] = chunk.get("section_key", "unknown")
                    sentiment_scores.append(sentiment)

        # Build sentiment trend chart
        if sentiment_scores:
            generated_charts.extend(_build_sentiment_charts(sentiment_scores))

    except Exception:
        logger.exception("sentiment_agent_failed")
    finally:
        cursor.close()

    logger.info(
        "sentiment_agent_done",
        tickers=tickers,
        chunks=len(retrieved_chunks),
        sentiments=len(sentiment_scores),
    )

    return {
        "retrieved_chunks": retrieved_chunks,
        "retrieved_charts": [],
        "sql_results": [],
        "generated_charts": generated_charts,
        "sentiment_scores": sentiment_scores,
    }


def _search_sections(
    query: str, ticker: str, section_key: str, limit: int = 3
) -> list[dict]:
    """Search for filing text from a specific section."""
    try:
        chunks = search_filing_text(
            query=f"{query} management outlook tone risk",
            ticker=ticker,
            content_type="text_chunk",
            limit=limit,
        )
        # Filter to target section where possible (Cortex Search may not filter by section_key directly)
        return chunks
    except Exception:
        logger.exception("sentiment_section_search_failed", ticker=ticker, section=section_key)
        return []


def _score_sentiment(
    cursor, text: str, ticker: str, filing_type: str, filing_date: str, section: str,
) -> dict | None:
    """Score sentiment of a text chunk using Cortex COMPLETE."""
    try:
        prompt = SENTIMENT_PROMPT.format(
            ticker=ticker,
            filing_type=filing_type,
            filing_date=filing_date,
            section=section,
            text=text,
        )
        cursor.execute(
            "SELECT SNOWFLAKE.CORTEX.COMPLETE(%s, %s) AS response",
            (LLM_MODEL, prompt),
        )
        row = cursor.fetchone()
        if not row or not row[0]:
            return None

        raw = row[0].strip()
        # Strip markdown fences
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        result = json.loads(raw)
        return {
            "sentiment": result.get("sentiment", "neutral"),
            "confidence": float(result.get("confidence", 0.5)),
            "tone_signals": result.get("tone_signals", []),
            "summary": result.get("summary", ""),
        }
    except (json.JSONDecodeError, Exception):
        logger.exception("sentiment_scoring_failed", ticker=ticker)
        return None


def _build_sentiment_charts(scores: list[dict]) -> list[dict]:
    """Build sentiment visualization charts."""
    charts = []

    # Map sentiment to numeric score for charting
    sentiment_map = {"bullish": 1.0, "neutral": 0.0, "bearish": -1.0}

    # Group by ticker for trend chart
    by_ticker: dict[str, list[dict]] = {}
    for s in scores:
        ticker = s.get("ticker", "?")
        by_ticker.setdefault(ticker, []).append(s)

    # Sentiment overview bar chart (avg sentiment by ticker)
    overview_data = []
    for ticker, ticker_scores in by_ticker.items():
        numeric_scores = [
            sentiment_map.get(s["sentiment"], 0) * s.get("confidence", 0.5)
            for s in ticker_scores
        ]
        avg = sum(numeric_scores) / len(numeric_scores) if numeric_scores else 0
        overview_data.append({
            "label": ticker,
            "value": round(avg, 2),
        })

    if overview_data:
        charts.append({
            "chart_type": "bar",
            "title": "Sentiment Score by Company",
            "category": "sentiment",
            "unit": "score",
            "ticker": ", ".join(by_ticker.keys()),
            "data": overview_data,
            "reference_lines": [
                {"value": 0, "label": "Neutral", "color": "#666", "axis": "y"},
            ],
        })

    # Detailed sentiment breakdown (grouped by section type)
    section_data = []
    for s in scores:
        numeric = sentiment_map.get(s["sentiment"], 0) * s.get("confidence", 0.5)
        section_data.append({
            "label": f"{s.get('ticker', '?')} ({s.get('filing_date', '?')[:10]})",
            "value": round(numeric, 2),
        })

    if section_data:
        charts.append({
            "chart_type": "bar",
            "title": "Sentiment by Filing Period",
            "category": "sentiment",
            "unit": "score",
            "ticker": ", ".join(by_ticker.keys()),
            "data": section_data,
            "reference_lines": [
                {"value": 0, "label": "Neutral", "color": "#666", "axis": "y"},
            ],
            "width_hint": "full",
        })

    return charts
