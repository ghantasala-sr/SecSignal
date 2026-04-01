"""Web search tool — calls the Snowflake Cortex Agent via SQL.

Uses SNOWFLAKE.CORTEX.AGENT_RUN to invoke the SECSIGNAL_WEB_AGENT
(which has web_search + cortex_search tools) for real-time market context.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import structlog

from secsignal.agents.connection import get_snowflake_connection

logger = structlog.get_logger(__name__)

_AGENT_FQN = "SECSIGNAL.RAW.SECSIGNAL_WEB_AGENT"
_LLM_MODEL = os.environ.get("CORTEX_LLM_MODEL", "claude-sonnet-4-6")

# ---------------------------------------------------------------------------
# Simple TTL cache for Cortex calls
# ---------------------------------------------------------------------------
_CACHE_TTL_SECONDS = 300  # 5 minutes

_search_cache: dict[str, tuple[float, tuple[str, list[dict[str, str]]]]] = {}
_chart_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _cache_key(query: str, tickers: list[str] | None) -> str:
    """Build a deterministic cache key from query + tickers."""
    t = ",".join(sorted(t.upper() for t in (tickers or [])))
    return f"{query.strip().lower()}||{t}"


def _get_search_cache(key: str) -> tuple[str, list[dict[str, str]]] | None:
    entry = _search_cache.get(key)
    if entry and (time.monotonic() - entry[0]) < _CACHE_TTL_SECONDS:
        logger.info("search_cache_hit", key=key[:60])
        return entry[1]
    _search_cache.pop(key, None)
    return None


def _get_chart_cache(key: str) -> list[dict[str, Any]] | None:
    entry = _chart_cache.get(key)
    if entry and (time.monotonic() - entry[0]) < _CACHE_TTL_SECONDS:
        logger.info("chart_cache_hit", key=key[:60])
        return entry[1]
    _chart_cache.pop(key, None)
    return None


def search_web_context(query: str, tickers: list[str] | None = None) -> tuple[str, list[dict[str, str]]]:
    """Call the Cortex Agent to search the web for current market context.

    Args:
        query: The user's original query about SEC filings.
        tickers: Optional list of ticker symbols to focus on.

    Returns:
        Tuple of (formatted text, list of web source dicts with title/url/snippet).
        Returns ("", []) on failure.
    """
    # Check cache first
    ck = _cache_key(query, tickers)
    cached = _get_search_cache(ck)
    if cached is not None:
        return cached

    ticker_str = ", ".join(tickers) if tickers else ""
    search_query = (
        f"Find the latest news, stock price, and analyst opinions for {ticker_str}. "
        f"Context: {query}"
    ) if ticker_str else (
        f"Find the latest market news and analyst opinions related to: {query}"
    )

    payload = {
        "agent": _AGENT_FQN,
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": search_query}],
            }
        ],
        "tools": [
            {"tool_spec": {"type": "web_search", "name": "web_search"}},
        ],
    }

    conn = get_snowflake_connection()
    cursor = conn.cursor()

    try:
        logger.info(
            "web_search_calling_agent",
            tickers=tickers,
            query_len=len(search_query),
        )

        payload_json = json.dumps(payload)
        cursor.execute(
            "SELECT SNOWFLAKE.CORTEX.AGENT_RUN(%s) AS response",
            (payload_json,),
        )
        row = cursor.fetchone()
        if not row or not row[0]:
            logger.warning("web_search_empty_response")
            return "", []

        raw = row[0]
        result = _parse_agent_response(raw)
        _search_cache[ck] = (time.monotonic(), result)
        return result

    except Exception:
        logger.exception("web_search_failed")
        return "", []
    finally:
        cursor.close()


def _parse_agent_response(raw: str) -> tuple[str, list[dict[str, str]]]:
    """Parse the JSON response from AGENT_RUN and extract useful text + sources.

    The response is a JSON string with a ``content`` array containing
    tool_use, tool_result, thinking, and text entries. We extract:
    1. Final text entries (the agent's synthesized answer)
    2. Search result snippets from tool_result entries as fallback
    3. Source URLs from tool_result entries for citation
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("web_search_parse_failed", raw_len=len(raw))
        return (raw[:2000] if raw else "", [])

    content = data.get("content", [])
    if not isinstance(content, list):
        return "", []

    # Collect final text blocks (the agent's answer)
    text_parts: list[str] = []
    # Collect search snippets as fallback
    snippets: list[str] = []
    # Collect structured web sources
    web_sources: list[dict[str, str]] = []

    for item in content:
        if not isinstance(item, dict):
            continue

        # Text response from the agent
        if item.get("type") == "text":
            text_parts.append(item.get("text", ""))

        # Search result snippets from tool_result entries
        if item.get("type") == "tool_result":
            _extract_snippets(item, snippets, web_sources)

    # Prefer the agent's synthesized text; fall back to raw snippets
    if text_parts:
        result = "\n".join(text_parts).strip()
    elif snippets:
        result = "\n\n".join(snippets[:10])
    else:
        result = ""

    # Deduplicate web sources by URL
    seen_urls: set[str] = set()
    unique_sources: list[dict[str, str]] = []
    for src in web_sources:
        url = src.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_sources.append(src)

    logger.info("web_search_result", result_len=len(result), sources=len(unique_sources))
    return result, unique_sources


def _extract_snippets(
    tool_result: dict[str, Any],
    snippets: list[str],
    web_sources: list[dict[str, str]],
) -> None:
    """Extract search result snippets and source citations from a tool_result content block."""
    content = tool_result.get("tool_result", {}).get("content", [])
    if not isinstance(content, list):
        return

    for entry in content:
        if not isinstance(entry, dict):
            continue
        json_data = entry.get("json", {})
        if not isinstance(json_data, dict):
            continue
        results = json_data.get("search_results", [])
        if not isinstance(results, list):
            continue

        for sr in results:
            if not isinstance(sr, dict):
                continue
            title = sr.get("DocTitle", "")
            text = sr.get("Text", "")
            url = sr.get("DocID", "")
            if text:
                # Strip HTML tags from snippet
                clean = re.sub(r"<[^>]+>", "", text)
                snippet = f"**{title}**\n{clean}"
                if url:
                    snippet += f"\nSource: {url}"
                snippets.append(snippet)
                # Build structured source citation
                if url:
                    web_sources.append({
                        "title": title or "Web source",
                        "url": url,
                        "snippet": clean[:200],
                    })


# ---------------------------------------------------------------------------
# Chart extraction from web search text
# ---------------------------------------------------------------------------

_EXTRACT_PROMPT = """Extract stock market data from the text below into JSON.
Return ONLY a JSON array. Each element must have these exact keys:
  - "ticker": string (e.g. "AAPL")
  - "current_price": number or null
  - "target_price": number or null
  - "change_percent": number or null (daily % change, e.g. -2.5)

If a value is not mentioned, use null. Only include tickers that have at
least one numeric value. Do NOT include any explanation — ONLY the JSON array.

Text:
{text}
"""


def generate_web_data_charts(
    web_context: str, tickers: list[str] | None = None
) -> list[dict[str, Any]]:
    """Extract structured chart data from web search text using Cortex LLM.

    Sends the web context to SNOWFLAKE.CORTEX.COMPLETE to pull out
    ticker → price/target pairs, then builds GeneratedChart-compatible
    dicts for the frontend.

    Args:
        web_context: The text returned by the web search agent.
        tickers: Optional list of tickers to filter results.

    Returns:
        List of chart dicts compatible with the GeneratedChart schema.
    """
    if not web_context or len(web_context) < 30:
        return []

    # Check cache first
    ck = _cache_key(web_context[:200], tickers)
    cached = _get_chart_cache(ck)
    if cached is not None:
        return cached

    conn = get_snowflake_connection()
    cursor = conn.cursor()

    try:
        prompt = _EXTRACT_PROMPT.format(text=web_context[:4000])
        cursor.execute(
            "SELECT SNOWFLAKE.CORTEX.COMPLETE(%s, %s) AS response",
            (_LLM_MODEL, prompt),
        )
        row = cursor.fetchone()
        if not row or not row[0]:
            return []

        raw = row[0].strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)

        entries = json.loads(raw)
        if not isinstance(entries, list):
            return []

        # Filter to requested tickers if provided
        if tickers:
            upper = {t.upper() for t in tickers}
            entries = [e for e in entries if e.get("ticker", "").upper() in upper]

        if not entries:
            return []

        charts: list[dict[str, Any]] = []

        # --- Chart 1: Current Price per ticker (bar chart) ---
        price_data = []
        for e in entries:
            price = e.get("current_price")
            if price is not None:
                price_data.append({
                    "label": e["ticker"],
                    "value": float(price),
                })
        if price_data:
            charts.append({
                "chart_type": "bar",
                "title": "Current Stock Prices",
                "category": "market_price",
                "unit": "USD",
                "ticker": "MARKET",
                "data": price_data,
            })

        # --- Chart 2: Grouped bar — Price vs Target (multi-series) ---
        grouped_data = []
        for e in entries:
            price = e.get("current_price")
            target = e.get("target_price")
            if price is not None and target is not None:
                grouped_data.append({
                    "label": e["ticker"],
                    "price": float(price),
                    "target": float(target),
                })
        if grouped_data:
            charts.append({
                "chart_type": "grouped_bar",
                "title": "Current Price vs Analyst Target",
                "category": "price_target",
                "unit": "USD",
                "ticker": "MARKET",
                "data": grouped_data,
                "series": [
                    {"key": "price", "name": "Current Price", "color": "#5eadad"},
                    {"key": "target", "name": "Analyst Target", "color": "#3B82F6"},
                ],
            })

        # --- Chart 3: Daily change % (bar chart) ---
        change_data = []
        for e in entries:
            chg = e.get("change_percent")
            if chg is not None:
                change_data.append({
                    "label": e["ticker"],
                    "value": float(chg),
                })
        if change_data:
            charts.append({
                "chart_type": "bar",
                "title": "Daily Price Change",
                "category": "price_change",
                "unit": "%",
                "ticker": "MARKET",
                "data": change_data,
            })

        logger.info("web_data_charts_generated", count=len(charts))
        _chart_cache[ck] = (time.monotonic(), charts)
        return charts

    except (json.JSONDecodeError, KeyError, TypeError):
        logger.exception("web_data_charts_parse_failed")
        return []
    except Exception:
        logger.exception("web_data_charts_failed")
        return []
    finally:
        cursor.close()
