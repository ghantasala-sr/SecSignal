"""Supervisor agent — classifies queries and plans execution.

Uses Cortex COMPLETE to:
1. Classify query type: trend / comparison / anomaly / general
2. Extract ticker symbols and time range
3. Detect visual intent (chart/graph keywords)
4. Plan which agent nodes to execute (replaces fixed routing)

The planner outputs an execution_plan — a list of node names to invoke
in parallel via LangGraph Send. This eliminates the bottleneck where
web_search_agent always ran, even for filing-only questions.
"""

from __future__ import annotations

import json
import os
from typing import Any, Union

import structlog
from langgraph.types import Send

from secsignal.agents.connection import get_snowflake_connection
from secsignal.agents.state import FilingState

logger = structlog.get_logger(__name__)

LLM_MODEL = os.environ.get("CORTEX_LLM_MODEL", "claude-sonnet-4-6")

# Valid agent nodes that the planner can include in execution_plan
VALID_AGENTS = {
    "trend_agent", "comparison_agent", "anomaly_agent", "general_agent",
    "web_search_agent", "valuation_agent", "sentiment_agent", "peer_group_agent",
}

PLANNING_PROMPT = """You are a financial query planner for an SEC filing analysis system. Analyze the user query and output a JSON object with these fields:

- "query_type": one of "trend", "comparison", "anomaly", "general"
  - "trend": questions about changes over time for a single company (e.g. "How has Apple's revenue changed?")
  - "comparison": questions comparing multiple companies (e.g. "Compare AAPL and MSFT risk factors")
  - "anomaly": questions about unusual changes, red flags, outliers (e.g. "Any unusual risk factor changes?")
  - "general": other questions about specific filings, factual lookups, or broad questions
- "tickers": list of ticker symbols mentioned or implied (e.g. ["AAPL", "MSFT"]). Use uppercase.
  Known tickers: AAPL, MSFT, GOOGL, AMZN, NVDA, TSLA
- "time_range": time period mentioned (e.g. "last 4 quarters", "2024-2025") or "all" if none specified
- "visual_intent": true if the user asks about charts, graphs, images, or visual data; false otherwise
- "execution_plan": a list of agent nodes to invoke. Choose from:
  - "trend_agent": retrieves financial metrics over time, generates trend charts. Use for single-company time-series questions.
  - "comparison_agent": retrieves and compares data across multiple companies. Use when 2+ tickers are involved.
  - "anomaly_agent": runs z-score anomaly detection on financial metrics. Use for outlier/red-flag questions.
  - "general_agent": does broad semantic search and SQL lookups across all filings. Use for factual questions, filing lookups, or when no specialist fits.
  - "valuation_agent": computes financial multiples (P/E, margins), revenue multiples, and basic DCF projections from extracted financials. Use for valuation questions, earnings multiples, financial health assessments, or "is X overvalued/undervalued" questions.
  - "sentiment_agent": analyzes tone and sentiment shifts in MD&A and risk factor sections across filing periods. Use for questions about management tone, optimism/pessimism, outlook changes, or "how has the tone changed" questions.
  - "peer_group_agent": compares a company against sector peers on financial metrics. Use for "how does X compare to peers", sector analysis, competitive positioning, or industry benchmarking questions.
  - "web_search_agent": searches the web for recent news, market context, or information NOT in SEC filings. ONLY include this when the query explicitly asks about recent news, market sentiment, stock price, current events, or information that would not be in SEC filings.

RULES for execution_plan:
1. Always include at least ONE primary specialist: trend_agent, comparison_agent, anomaly_agent, valuation_agent, sentiment_agent, peer_group_agent, or general_agent.
2. You may combine specialists when the query spans multiple domains (e.g. valuation + sentiment, or comparison + peer_group).
3. ONLY add "web_search_agent" if the query needs external/web information. Most filing questions do NOT need web search.
4. If unsure whether web search is needed, do NOT include it. Filing data is sufficient for most questions.

Examples:
- "How has Apple's revenue changed over the last 4 quarters?" → ["trend_agent"]
- "Compare AAPL and MSFT risk factors" → ["comparison_agent"]
- "Any unusual changes in NVDA's financials?" → ["anomaly_agent"]
- "What did Tesla say about supply chain risks?" → ["general_agent"]
- "What is NVDA's P/E ratio and how does their valuation look?" → ["valuation_agent"]
- "How has Tesla's management tone changed in recent filings?" → ["sentiment_agent"]
- "How does MSFT compare to other cloud companies?" → ["peer_group_agent"]
- "Is NVDA overvalued compared to peers?" → ["valuation_agent", "peer_group_agent"]
- "What's the latest news on AAPL earnings and how does it compare to their filing?" → ["trend_agent", "web_search_agent"]
- "How is NVDA stock performing after their latest 10-K?" → ["general_agent", "web_search_agent"]

IMPORTANT: If there is prior conversation context, the user may use pronouns or references like "what about MSFT?", "compare that with Tesla", "now show me anomalies". Resolve these references using the conversation history below.

{conversation_context}

Output ONLY valid JSON, no markdown or explanation.

User query: {query}"""


def classify_query(state: FilingState) -> FilingState:
    """Classify the user query, extract metadata, and plan execution.

    This is the first node in the LangGraph — runs before fan-out routing.
    Now also produces an execution_plan for Send-based conditional fan-out.
    """
    query = state["query"]
    conn = get_snowflake_connection()
    cursor = conn.cursor()

    try:
        # Format conversation context for the planner
        history = state.get("conversation_history", [])
        if history:
            context_parts = []
            for turn in history[-4:]:  # last 2 exchanges
                role = "User" if turn.get("role") == "user" else "Assistant"
                content = turn.get("content", "")[:500]
                context_parts.append(f"{role}: {content}")
            conversation_context = "Prior conversation:\n" + "\n".join(context_parts)
        else:
            conversation_context = "No prior conversation."

        prompt = PLANNING_PROMPT.format(query=query, conversation_context=conversation_context)

        cursor.execute(
            "SELECT SNOWFLAKE.CORTEX.COMPLETE(%s, %s) AS response",
            (LLM_MODEL, prompt),
        )
        row = cursor.fetchone()
        raw_response = row[0] if row else "{}"

        # Parse the LLM JSON response
        parsed = _parse_classification(raw_response, query)

        # Validate tickers against our filing database
        unknown_tickers = []
        if parsed["tickers"]:
            unknown_tickers = _find_unknown_tickers(parsed["tickers"], cursor)
            if unknown_tickers:
                # Auto-add web_search_agent for tickers we don't have filings for
                if "web_search_agent" not in parsed["execution_plan"]:
                    parsed["execution_plan"].append("web_search_agent")
                logger.info(
                    "unknown_tickers_detected",
                    unknown=unknown_tickers,
                    known=[t for t in parsed["tickers"] if t not in unknown_tickers],
                )

        logger.info(
            "query_classified",
            query=query[:60],
            query_type=parsed["query_type"],
            tickers=parsed["tickers"],
            execution_plan=parsed["execution_plan"],
            visual_intent=parsed["visual_intent"],
        )

        return {
            **state,
            "query_type": parsed["query_type"],
            "tickers": parsed["tickers"],
            "time_range": parsed["time_range"],
            "visual_intent": parsed["visual_intent"],
            "execution_plan": parsed["execution_plan"],
            "unknown_tickers": unknown_tickers,
        }

    except Exception:
        logger.exception("classify_query_failed", query=query[:60])
        # Fall back to general_agent only (no web search)
        return {
            **state,
            "query_type": "general",
            "tickers": state.get("tickers", []),
            "time_range": state.get("time_range", "all"),
            "visual_intent": False,
            "execution_plan": ["general_agent"],
            "unknown_tickers": [],
        }
    finally:
        cursor.close()


def route_plan(state: FilingState) -> list[Union[str, Send]]:
    """Fan-out to the agents listed in execution_plan using LangGraph Send.

    Returns a list of Send objects, one per planned agent node.
    LangGraph will invoke them in parallel and merge results via
    the operator.add annotations on list fields in FilingState.
    """
    plan = state.get("execution_plan", [])

    # Safety: if plan is empty, default to general_agent
    if not plan:
        plan = ["general_agent"]

    sends = []
    for node_name in plan:
        if node_name in VALID_AGENTS:
            sends.append(Send(node_name, state))
        else:
            logger.warning("invalid_plan_node", node=node_name)

    # Guarantee at least one node runs
    if not sends:
        sends.append(Send("general_agent", state))

    logger.info("route_plan", nodes=[s.node for s in sends])
    return sends


# Keep old route_query for backward compatibility during transition
def route_query(state: FilingState) -> str:
    """Legacy routing — kept for reference. Use route_plan instead."""
    query_type = state.get("query_type", "general")
    mapping = {
        "trend": "trend_agent",
        "comparison": "comparison_agent",
        "anomaly": "anomaly_agent",
    }
    return mapping.get(query_type, "general_agent")


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
            "execution_plan": ["general_agent"],
        }

    # Validate and normalize query_type
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

    # Parse and validate execution_plan
    execution_plan = parsed.get("execution_plan", [])
    if isinstance(execution_plan, str):
        execution_plan = [execution_plan]
    execution_plan = [n for n in execution_plan if n in VALID_AGENTS]

    # Ensure at least one specialist is in the plan
    specialists = {
        "trend_agent", "comparison_agent", "anomaly_agent", "general_agent",
        "valuation_agent", "sentiment_agent", "peer_group_agent",
    }
    has_specialist = any(n in specialists for n in execution_plan)
    if not has_specialist:
        # Map query_type to default specialist
        type_to_agent = {
            "trend": "trend_agent",
            "comparison": "comparison_agent",
            "anomaly": "anomaly_agent",
            "general": "general_agent",
        }
        default_agent = type_to_agent.get(query_type, "general_agent")
        execution_plan.insert(0, default_agent)

    return {
        "query_type": query_type,
        "tickers": tickers,
        "time_range": parsed.get("time_range", "all"),
        "visual_intent": visual_intent,
        "execution_plan": execution_plan,
    }


def _find_unknown_tickers(tickers: list[str], cursor) -> list[str]:
    """Check which tickers have no data in our filing database.

    Queries across all three main tables to see if a ticker exists anywhere.
    Returns the list of tickers that have zero rows in our system.
    """
    if not tickers:
        return []

    placeholders = ", ".join(["%s"] * len(tickers))
    sql = f"""
        SELECT DISTINCT TICKER FROM (
            SELECT TICKER FROM SECSIGNAL.RAW.EXTRACTED_FINANCIALS WHERE TICKER IN ({placeholders})
            UNION
            SELECT TICKER FROM SECSIGNAL.MARTS.FCT_RISK_FACTORS WHERE TICKER IN ({placeholders})
            UNION
            SELECT TICKER FROM SECSIGNAL.MARTS.FCT_FINANCIALS WHERE TICKER IN ({placeholders})
        )
    """
    upper_tickers = [t.upper() for t in tickers]
    try:
        cursor.execute(sql, upper_tickers * 3)
        known = {row[0] for row in cursor.fetchall()}
        return [t for t in upper_tickers if t not in known]
    except Exception:
        logger.exception("ticker_validation_failed")
        return []
