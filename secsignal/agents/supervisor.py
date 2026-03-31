"""Supervisor agent — classifies queries and routes to specialist agents.

Uses Cortex COMPLETE (mistral-large2) to:
1. Classify query type: trend / comparison / anomaly / general
2. Extract ticker symbols and time range
3. Detect visual intent (chart/graph keywords)
4. Route to the appropriate specialist node
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

CLASSIFICATION_PROMPT = """You are a financial query classifier for SEC filings. Analyze the user query and output a JSON object with these fields:

- "query_type": one of "trend", "comparison", "anomaly", "general"
  - "trend": questions about changes over time for a single company (e.g. "How has Apple's revenue changed?")
  - "comparison": questions comparing multiple companies (e.g. "Compare AAPL and MSFT risk factors")
  - "anomaly": questions about unusual changes, red flags, outliers (e.g. "Any unusual risk factor changes?")
  - "general": other questions about specific filings or factual lookups
- "tickers": list of ticker symbols mentioned or implied (e.g. ["AAPL", "MSFT"]). Use uppercase.
  Known tickers: AAPL, MSFT, GOOGL, AMZN, NVDA, TSLA
- "time_range": time period mentioned (e.g. "last 4 quarters", "2024-2025") or "all" if none specified
- "visual_intent": true if the user asks about charts, graphs, images, or visual data; false otherwise

Output ONLY valid JSON, no markdown or explanation.

User query: {query}"""


def classify_query(state: FilingState) -> FilingState:
    """Classify the user query and extract routing metadata.

    This is the first node in the LangGraph — runs before specialist routing.
    """
    query = state["query"]
    conn = get_snowflake_connection()
    cursor = conn.cursor()

    try:
        prompt = CLASSIFICATION_PROMPT.format(query=query)

        cursor.execute(
            "SELECT SNOWFLAKE.CORTEX.COMPLETE(%s, %s) AS response",
            (LLM_MODEL, prompt),
        )
        row = cursor.fetchone()
        raw_response = row[0] if row else "{}"

        # Parse the LLM JSON response
        parsed = _parse_classification(raw_response, query)

        logger.info(
            "query_classified",
            query=query[:60],
            query_type=parsed["query_type"],
            tickers=parsed["tickers"],
            visual_intent=parsed["visual_intent"],
        )

        return {
            **state,
            "query_type": parsed["query_type"],
            "tickers": parsed["tickers"],
            "time_range": parsed["time_range"],
            "visual_intent": parsed["visual_intent"],
        }

    except Exception:
        logger.exception("classify_query_failed", query=query[:60])
        # Fall back to general with no tickers
        return {
            **state,
            "query_type": "general",
            "tickers": state.get("tickers", []),
            "time_range": state.get("time_range", "all"),
            "visual_intent": False,
        }
    finally:
        cursor.close()


def route_query(state: FilingState) -> str:
    """Route to the appropriate specialist based on query_type.

    Returns the node name for LangGraph conditional routing.
    """
    query_type = state.get("query_type", "general")
    if query_type == "trend":
        return "trend_agent"
    elif query_type == "comparison":
        return "comparison_agent"
    elif query_type == "anomaly":
        return "anomaly_agent"
    else:
        # General queries go through trend agent as default
        return "trend_agent"


def _parse_classification(raw: str, original_query: str = "") -> dict[str, Any]:
    """Parse LLM classification response, handling edge cases."""
    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (fences)
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("classification_parse_failed", raw=text[:200])
        return {
            "query_type": "general",
            "tickers": [],
            "time_range": "all",
            "visual_intent": False,
        }

    # Validate and normalize
    valid_types = {"trend", "comparison", "anomaly", "general"}
    query_type = parsed.get("query_type", "general")
    if query_type not in valid_types:
        query_type = "general"

    tickers = parsed.get("tickers", [])
    if isinstance(tickers, str):
        tickers = [tickers]
    tickers = [t.upper() for t in tickers if isinstance(t, str)]

    # LLM visual_intent + keyword fallback for robustness
    visual_intent = bool(parsed.get("visual_intent", False))
    visual_keywords = {"chart", "charts", "graph", "graphs", "image", "images",
                       "visual", "picture", "diagram", "figure", "plot"}
    if not visual_intent and original_query:
        visual_intent = bool(visual_keywords & set(original_query.lower().split()))

    return {
        "query_type": query_type,
        "tickers": tickers,
        "time_range": parsed.get("time_range", "all"),
        "visual_intent": visual_intent,
    }
