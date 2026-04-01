"""Web search agent node — enriches state with real-time market context.

Calls the Snowflake Cortex Agent (SECSIGNAL_WEB_AGENT) to fetch current
market news, stock prices, and analyst opinions for the queried tickers.
Runs between specialist agents and the synthesizer in the graph.
"""

from __future__ import annotations

import structlog

from secsignal.agents.state import FilingState
from secsignal.agents.tools.web_search_tool import (
    generate_web_data_charts,
    search_web_context,
)

logger = structlog.get_logger(__name__)


def web_search_agent(state: FilingState) -> dict:
    """Fetch real-time web context for the query and tickers.

    Builds a search query from the user's question and extracted tickers,
    then calls the Cortex Agent web search tool.

    Returns:
        Dict with ``web_context`` string for the synthesizer.
    """
    query = state["query"]
    tickers = state.get("tickers", [])

    logger.info("web_search_agent_start", query=query[:60], tickers=tickers)

    web_context, web_sources = search_web_context(query=query, tickers=tickers)

    if web_context:
        logger.info(
            "web_search_agent_done",
            context_len=len(web_context),
            tickers=tickers,
            web_sources=len(web_sources),
        )
    else:
        logger.warning("web_search_agent_empty", tickers=tickers)

    # Extract structured chart data from web search text
    web_charts = generate_web_data_charts(web_context, tickers=tickers)
    logger.info("web_search_charts", chart_count=len(web_charts))

    return {
        "web_context": web_context,
        "web_sources": web_sources,
        "generated_charts": web_charts,
    }
