"""Synthesizer node — merges retrieved data and generates cited answers.

Takes all retrieved chunks, SQL results, charts, and anomaly scores from
specialist agents and produces a final answer via Cortex COMPLETE.
"""

from __future__ import annotations

import json
import os
from typing import Any

import structlog

from secsignal.agents.connection import get_snowflake_connection
from secsignal.agents.state import FilingState

logger = structlog.get_logger(__name__)

LLM_MODEL = os.environ.get("CORTEX_LLM_MODEL", "mistral-large2")

SYNTHESIS_PROMPT = """You are a senior financial analyst synthesizing SEC filing intelligence. Based on the retrieved data below, produce a comprehensive answer to the user's query.

**User Query:** {query}
**Query Type:** {query_type}

**Retrieved Filing Text (from Cortex Search):**
{text_context}

**Structured Data (from SQL marts):**
{sql_context}

{anomaly_context}

{chart_context}

**Instructions:**
1. Provide a clear, well-structured answer citing specific data points.
2. When referencing filing data, mention the company ticker, filing date, and filing type.
3. If anomalies were detected, explain their significance (z-score meaning, direction of change).
4. For comparisons, use a structured format with clear company-by-company breakdown.
5. If chart data is available, reference the chart descriptions in your analysis.
6. Keep the response concise but thorough — 2-4 paragraphs for typical queries.
7. End with a brief "Sources" section listing the filings referenced.

Answer:"""


def synthesizer(state: FilingState) -> dict:
    """Generate the final cited answer from all retrieved data.

    Merges text chunks, SQL results, anomaly scores, and chart metadata
    into a structured prompt, then calls Cortex COMPLETE for synthesis.
    """
    query = state["query"]
    query_type = state.get("query_type", "general")
    retrieved_chunks = state.get("retrieved_chunks", [])
    sql_results = state.get("sql_results", [])
    anomaly_scores = state.get("anomaly_scores", [])
    retrieved_charts = state.get("retrieved_charts", [])

    # Format text context
    text_context = _format_text_chunks(retrieved_chunks)

    # Format SQL context
    sql_context = _format_sql_results(sql_results)

    # Format anomaly context
    anomaly_context = _format_anomalies(anomaly_scores)

    # Format chart context (descriptions only, not base64 data)
    chart_context = _format_charts(retrieved_charts)

    prompt = SYNTHESIS_PROMPT.format(
        query=query,
        query_type=query_type,
        text_context=text_context or "No text results retrieved.",
        sql_context=sql_context or "No structured data retrieved.",
        anomaly_context=anomaly_context,
        chart_context=chart_context,
    )

    conn = get_snowflake_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT SNOWFLAKE.CORTEX.COMPLETE(%s, %s) AS response",
            (LLM_MODEL, prompt),
        )
        row = cursor.fetchone()
        answer = row[0] if row else "Unable to generate response."

        # Build source citations
        sources = _build_sources(retrieved_chunks, sql_results)

        logger.info(
            "synthesizer_done",
            query_type=query_type,
            answer_len=len(answer),
            sources=len(sources),
        )

        return {
            "final_answer": answer,
            "sources": sources,
        }

    except Exception:
        logger.exception("synthesizer_failed")
        return {
            "final_answer": "An error occurred while generating the response. Please try again.",
            "sources": [],
        }
    finally:
        cursor.close()


def _format_text_chunks(chunks: list[dict[str, Any]]) -> str:
    """Format retrieved text chunks for the synthesis prompt."""
    if not chunks:
        return ""
    parts = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(
            f"[{i}] ({chunk.get('ticker', '?')} | {chunk.get('filing_type', '?')} | "
            f"{chunk.get('filing_date', '?')} | score: {chunk.get('score', 0):.3f})\n"
            f"{chunk.get('content', '')[:800]}"
        )
    return "\n\n".join(parts)


def _format_sql_results(results: list[dict[str, Any]]) -> str:
    """Format SQL query results for the synthesis prompt."""
    if not results:
        return ""
    parts = []
    for r in results[:20]:  # Limit to avoid prompt overflow
        source = r.get("source", "unknown")
        ticker = r.get("ticker", "?")
        date = r.get("filing_date", "?")
        if source == "extracted_financials":
            name = r.get("metric_name", "?")
            value = r.get("value", 0)
            unit = r.get("unit", "")
            period = r.get("period", "")
            if unit == "USD_millions":
                parts.append(f"- {ticker} ({period or date}): {name} = ${value:,.0f}M")
            elif unit == "percent":
                parts.append(f"- {ticker} ({period or date}): {name} = {value:.1f}%")
            else:
                parts.append(f"- {ticker} ({period or date}): {name} = {value:,.2f} {unit}")
        elif source == "fct_risk_factors":
            wc = r.get("word_count", 0)
            delta = r.get("word_count_delta", 0)
            parts.append(f"- {ticker} ({date}): risk factors {wc:,} words, delta {delta:+,}")
        elif source == "fct_financials":
            section = r.get("section_key", "?")
            wc = r.get("word_count", 0)
            parts.append(f"- {ticker} ({date}): {section} — {wc:,} words")
        else:
            parts.append(f"- {ticker} ({date}): {json.dumps(r, default=str)[:200]}")
    return "\n".join(parts)


def _format_anomalies(anomalies: list[dict[str, Any]]) -> str:
    """Format anomaly scores for the synthesis prompt."""
    if not anomalies:
        return ""
    parts = ["**Detected Anomalies (z-score > 2.0):**"]
    for a in anomalies:
        direction = a.get("direction", "?")
        z = a.get("z_score", 0)
        parts.append(
            f"- {a.get('ticker', '?')} ({a.get('filing_date', '?')}): "
            f"{a.get('metric', '?')} = {a.get('value', 0):+,} "
            f"(z={z:+.2f}, {direction})"
        )
    return "\n".join(parts)


def _format_charts(charts: list[dict[str, Any]]) -> str:
    """Format chart descriptions for the synthesis prompt."""
    if not charts:
        return ""
    parts = ["**Available Charts:**"]
    for c in charts:
        desc = c.get("description", "No description")
        parts.append(
            f"- [{c.get('ticker', '?')} | {c.get('chart_type', '?')} | "
            f"{c.get('filing_date', '?')}] {desc}"
        )
    return "\n".join(parts)


def _build_sources(
    chunks: list[dict[str, Any]],
    sql_results: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Deduplicate and build source citations."""
    seen = set()
    sources = []
    for chunk in chunks:
        key = (chunk.get("ticker", ""), chunk.get("filing_date", ""), chunk.get("filing_type", ""))
        if key not in seen:
            seen.add(key)
            sources.append({
                "ticker": chunk.get("ticker", ""),
                "filing_date": chunk.get("filing_date", ""),
                "filing_type": chunk.get("filing_type", ""),
                "content_type": chunk.get("content_type", ""),
            })
    for r in sql_results:
        key = (r.get("ticker", ""), r.get("filing_date", ""), r.get("source", ""))
        if key not in seen:
            seen.add(key)
            sources.append({
                "ticker": r.get("ticker", ""),
                "filing_date": r.get("filing_date", ""),
                "filing_type": r.get("filing_type", r.get("source", "")),
                "content_type": "structured_data",
            })
    return sources
