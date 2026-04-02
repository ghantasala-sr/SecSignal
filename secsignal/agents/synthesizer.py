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

LLM_MODEL = os.environ.get("CORTEX_LLM_MODEL", "claude-sonnet-4-6")

SYNTHESIS_PROMPT = """You are an elite sell-side equity research analyst producing institutional-grade SEC filing intelligence. Your readers are portfolio managers who need actionable insight, not summaries.

{conversation_history}

**User Query:** {query}
**Query Type:** {query_type}

**Retrieved Filing Text (from Cortex Search):**
{text_context}

**Structured Data (from SQL marts):**
{sql_context}

{anomaly_context}

{chart_context}

{web_context}

{unknown_tickers_context}

**Analysis Standards — follow these strictly:**

1. **Lead with the signal, not the data.** Open with the most material finding and its business implication. Never start with "Based on the data..." or restate the query.

2. **Quantify everything.** Every claim must cite specific numbers — dollar amounts, percentages, word counts, z-scores, filing dates. Vague language like "significant increase" is unacceptable; say "$2.3B increase in R&D (+18% YoY)" instead.

3. **Explain the business impact.** For every data point, answer: "So what does this mean for revenue, margins, or risk exposure?" Connect filing language to real financial consequences.
   - BAD: "Apple's tariff-related risk language is worth monitoring."
   - GOOD: "Tariff risk is likely to transition from narrative mention to formal risk factor if trade tensions escalate, given Apple's heavy reliance on China-based manufacturing (~90% of iPhone assembly), which directly impacts gross margins."

4. **Be specific about causality.** Don't just report what changed — explain WHY it changed and what it signals about the company's strategic direction.

5. **For anomalies:** Explain what a z-score means in plain terms (e.g., "a z-score of +3.2 means this metric is 3.2 standard deviations above the company's historical norm — a statistically rare event"). Then state what could cause it and what it implies for future filings or earnings.

6. **For comparisons:** Don't just list differences — rank companies by risk exposure or metric strength and explain who is better/worse positioned and why.

7. **For trends:** Identify inflection points — where did the trajectory change, and what external or strategic event likely caused it?

8. **End with a sharp forward-looking verdict.** State the probable trajectory: what is likely to happen next based on the evidence? Give a clear directional view, not hedged platitudes.

9. **Structure:** Use markdown with clear headers (##), bold key figures, and bullet points for data-dense sections. Keep it 3-5 paragraphs — dense but readable.

10. **Source references:** When citing filing data, always include (TICKER, filing type, filing date) inline.

11. **ALWAYS include a summary data table.** For every response that involves numeric data (prices, financials, risk metrics, comparisons), you MUST include at least one GitHub-Flavored Markdown pipe table. Use `| Column | Column |` with `|---|---|` separator rows. Align numeric columns right. Example:
    | Ticker | Revenue ($M) | YoY Growth |
    |--------|-------------:|-----------:|
    | AAPL   |       94,836 |      +4.2% |
    This is mandatory — never present numeric comparisons as plain prose when a table would be clearer.

12. **Chart-friendly data.** When presenting current market data (stock prices, analyst targets, percentage changes), always organize them in a table with consistent columns so the data can be visualized. Include exact numeric values (not ranges) wherever possible.

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
    web_context_raw = state.get("web_context", "")
    history_raw = state.get("conversation_history", [])
    unknown_tickers = state.get("unknown_tickers", [])

    # Format text context
    text_context = _format_text_chunks(retrieved_chunks)

    # Format SQL context
    sql_context = _format_sql_results(sql_results)

    # Format anomaly context
    anomaly_context = _format_anomalies(anomaly_scores)

    # Format chart context (descriptions only, not base64 data)
    chart_context = _format_charts(retrieved_charts)

    # Format web context
    web_context = _format_web_context(web_context_raw)

    # Format unknown tickers notice
    unknown_tickers_context = _format_unknown_tickers(unknown_tickers)

    # Format conversation history
    conversation_history = _format_conversation_history(history_raw)

    prompt = SYNTHESIS_PROMPT.format(
        query=query,
        query_type=query_type,
        text_context=text_context or "No text results retrieved.",
        sql_context=sql_context or "No structured data retrieved.",
        anomaly_context=anomaly_context,
        chart_context=chart_context,
        web_context=web_context,
        unknown_tickers_context=unknown_tickers_context,
        conversation_history=conversation_history,
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


def _format_web_context(web_context: str) -> str:
    """Format web search results for the synthesis prompt."""
    if not web_context:
        return ""
    return (
        "**Real-Time Market Context (from web search — use to add current perspective, "
        "but always prioritize SEC filing data as the authoritative source):**\n"
        f"{web_context[:3000]}"
    )


def _format_conversation_history(history: list[dict[str, str]]) -> str:
    """Format recent conversation turns for context in follow-up queries."""
    if not history:
        return ""
    # Take last 3 exchanges (6 turns max) to keep prompt manageable
    recent = history[-6:]
    parts = ["**Prior Conversation (use for context — the current query may be a follow-up):**"]
    for turn in recent:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        # Truncate long assistant responses to keep prompt size reasonable
        if role == "assistant":
            content = content[:1500] + ("..." if len(content) > 1500 else "")
        prefix = "User" if role == "user" else "Assistant"
        parts.append(f"**{prefix}:** {content}")
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


def _format_unknown_tickers(unknown_tickers: list[str]) -> str:
    """Format notice about tickers not found in our filing database."""
    if not unknown_tickers:
        return ""
    ticker_list = ", ".join(unknown_tickers)
    return (
        f"**IMPORTANT — No Filing Data Available:** The following tickers are NOT in our SEC filing database: "
        f"**{ticker_list}**. We only have filings for AAPL, AMZN, GOOGL, MSFT, NVDA, and TSLA. "
        f"You MUST clearly tell the user that we do not have SEC filing data for {ticker_list}. "
        f"If web search results are available above, use them to provide what information you can, "
        f"but explicitly state that it comes from web sources, not SEC filings. "
        f"If no web results are available either, tell the user we have no data for these tickers "
        f"and suggest they ask about one of the supported tickers instead."
    )
