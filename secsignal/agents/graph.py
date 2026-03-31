"""LangGraph graph definition — wires supervisor → specialists → synthesizer.

The SecSignal agent graph:
    START → classify_query → route → [trend_agent | comparison_agent | anomaly_agent] → synthesizer → END

Uses LangGraph StateGraph with conditional routing based on query classification.
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from secsignal.agents.state import FilingState
from secsignal.agents.supervisor import classify_query, route_query
from secsignal.agents.trend_agent import trend_agent
from secsignal.agents.comparison_agent import comparison_agent
from secsignal.agents.anomaly_agent import anomaly_agent
from secsignal.agents.synthesizer import synthesizer


def build_graph() -> StateGraph:
    """Build and compile the SecSignal LangGraph agent system.

    Graph topology:
        classify_query → conditional_route → specialist → synthesizer → END

    Returns:
        Compiled LangGraph runnable.
    """
    graph = StateGraph(FilingState)

    # Add nodes
    graph.add_node("classify_query", classify_query)
    graph.add_node("trend_agent", trend_agent)
    graph.add_node("comparison_agent", comparison_agent)
    graph.add_node("anomaly_agent", anomaly_agent)
    graph.add_node("synthesizer", synthesizer)

    # Entry point
    graph.set_entry_point("classify_query")

    # Conditional routing from supervisor to specialist
    graph.add_conditional_edges(
        "classify_query",
        route_query,
        {
            "trend_agent": "trend_agent",
            "comparison_agent": "comparison_agent",
            "anomaly_agent": "anomaly_agent",
        },
    )

    # All specialists flow into synthesizer
    graph.add_edge("trend_agent", "synthesizer")
    graph.add_edge("comparison_agent", "synthesizer")
    graph.add_edge("anomaly_agent", "synthesizer")

    # Synthesizer is the terminal node
    graph.add_edge("synthesizer", END)

    return graph.compile()


# Module-level compiled graph (singleton)
agent_graph = build_graph()


def run_query(query: str, tickers: list[str] | None = None) -> dict:
    """Run a query through the SecSignal agent system.

    Args:
        query: Natural language question about SEC filings.
        tickers: Optional list of ticker symbols to focus on.

    Returns:
        Dict with final_answer, sources, retrieved_charts, anomaly_scores.
    """
    initial_state: FilingState = {
        "query": query,
        "query_type": "general",
        "tickers": tickers or [],
        "time_range": "all",
        "visual_intent": False,
        "retrieved_chunks": [],
        "retrieved_charts": [],
        "sql_results": [],
        "anomaly_scores": [],
        "generated_charts": [],
        "final_answer": "",
        "sources": [],
    }

    result = agent_graph.invoke(initial_state)

    return {
        "query": query,
        "query_type": result.get("query_type", "general"),
        "tickers": result.get("tickers", []),
        "final_answer": result.get("final_answer", ""),
        "sources": result.get("sources", []),
        "retrieved_charts": result.get("retrieved_charts", []),
        "anomaly_scores": result.get("anomaly_scores", []),
        "generated_charts": result.get("generated_charts", []),
    }
