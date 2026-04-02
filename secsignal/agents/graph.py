"""LangGraph graph definition — planner → [dynamic fan-out] → synthesizer.

The SecSignal agent graph:
    START → classify_query → route_plan → [Send to selected agents] → synthesizer → END

Uses LangGraph Send for conditional fan-out: the planner decides which agents
to invoke (e.g. just trend_agent, or trend_agent + web_search_agent), and only
those run. This eliminates the old bottleneck where web_search_agent always ran.
"""

from __future__ import annotations

import json
import time
from collections.abc import Generator
from typing import Any

from langgraph.graph import END, StateGraph

from secsignal.agents.state import FilingState
from secsignal.agents.supervisor import classify_query, route_plan
from secsignal.agents.trend_agent import trend_agent
from secsignal.agents.comparison_agent import comparison_agent
from secsignal.agents.anomaly_agent import anomaly_agent
from secsignal.agents.general_agent import general_agent
from secsignal.agents.synthesizer import synthesizer
from secsignal.agents.web_search_agent import web_search_agent


def build_graph() -> StateGraph:
    """Build and compile the SecSignal LangGraph agent system.

    Graph topology:
        classify_query → route_plan (Send fan-out) → [selected agents] → synthesizer → END

    The planner's execution_plan determines which agents run. All selected
    agents run in parallel (via Send), their results merge via operator.add
    annotations, then synthesizer produces the final answer.

    Returns:
        Compiled LangGraph runnable.
    """
    graph = StateGraph(FilingState)

    # Add nodes
    graph.add_node("classify_query", classify_query)
    graph.add_node("trend_agent", trend_agent)
    graph.add_node("comparison_agent", comparison_agent)
    graph.add_node("anomaly_agent", anomaly_agent)
    graph.add_node("general_agent", general_agent)
    graph.add_node("web_search_agent", web_search_agent)
    graph.add_node("synthesizer", synthesizer)

    # Entry point
    graph.set_entry_point("classify_query")

    # Conditional fan-out from planner using Send
    # route_plan returns list[Send] based on execution_plan
    graph.add_conditional_edges(
        "classify_query",
        route_plan,
        [
            "trend_agent",
            "comparison_agent",
            "anomaly_agent",
            "general_agent",
            "web_search_agent",
        ],
    )

    # All agent nodes converge to synthesizer
    graph.add_edge("trend_agent", "synthesizer")
    graph.add_edge("comparison_agent", "synthesizer")
    graph.add_edge("anomaly_agent", "synthesizer")
    graph.add_edge("general_agent", "synthesizer")
    graph.add_edge("web_search_agent", "synthesizer")

    # Synthesizer is the terminal node
    graph.add_edge("synthesizer", END)

    return graph.compile()


# Module-level compiled graph (singleton)
agent_graph = build_graph()


def run_query(query: str, tickers: list[str] | None = None, conversation_history: list[dict[str, str]] | None = None) -> dict:
    """Run a query through the SecSignal agent system.

    Args:
        query: Natural language question about SEC filings.
        tickers: Optional list of ticker symbols to focus on.
        conversation_history: Optional list of prior {role, content} turns.

    Returns:
        Dict with final_answer, sources, retrieved_charts, anomaly_scores.
    """
    initial_state: FilingState = {
        "query": query,
        "query_type": "general",
        "tickers": tickers or [],
        "time_range": "all",
        "visual_intent": False,
        "execution_plan": [],
        "unknown_tickers": [],
        "retrieved_chunks": [],
        "retrieved_charts": [],
        "sql_results": [],
        "anomaly_scores": [],
        "generated_charts": [],
        "web_context": "",
        "web_sources": [],
        "conversation_history": conversation_history or [],
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
        "web_sources": result.get("web_sources", []),
    }


# Human-readable labels for each graph node
_NODE_LABELS: dict[str, str] = {
    "classify_query": "Planning execution & classifying query",
    "trend_agent": "Running trend analysis",
    "comparison_agent": "Running comparison analysis",
    "anomaly_agent": "Running anomaly detection",
    "general_agent": "Running general filing lookup",
    "web_search_agent": "Searching web for real-time market context",
    "synthesizer": "Synthesizing final answer",
}


def _extract_step_detail(node: str, state_update: dict[str, Any]) -> dict[str, Any]:
    """Pull salient fields from a node's state update for the trajectory event."""
    if node == "classify_query":
        return {
            "query_type": state_update.get("query_type", "general"),
            "tickers": state_update.get("tickers", []),
            "execution_plan": state_update.get("execution_plan", []),
        }
    if node in ("trend_agent", "comparison_agent", "anomaly_agent", "general_agent"):
        return {
            "chunks_retrieved": len(state_update.get("retrieved_chunks", [])),
            "charts_retrieved": len(state_update.get("retrieved_charts", [])),
            "charts_generated": len(state_update.get("generated_charts", [])),
            "anomalies_found": len(state_update.get("anomaly_scores", [])),
        }
    if node == "web_search_agent":
        ctx = state_update.get("web_context", "")
        return {
            "context_length": len(ctx),
            "has_results": bool(ctx),
        }
    if node == "synthesizer":
        answer = state_update.get("final_answer", "")
        return {
            "answer_length": len(answer),
            "sources_count": len(state_update.get("sources", [])),
        }
    return {}


def run_query_stream(
    query: str, tickers: list[str] | None = None, conversation_history: list[dict[str, str]] | None = None,
) -> Generator[str, None, None]:
    """Stream query execution through the agent graph, yielding SSE events.

    Yields newline-delimited JSON strings (one per line) suitable for
    Server-Sent Events.  Each event is one of:
      - ``{"event": "step", ...}``  -- a graph node completed
      - ``{"event": "result", ...}`` -- final result payload

    Args:
        query: Natural language question about SEC filings.
        tickers: Optional list of ticker symbols to focus on.
        conversation_history: Optional list of prior {role, content} turns.
    """
    initial_state: FilingState = {
        "query": query,
        "query_type": "general",
        "tickers": tickers or [],
        "time_range": "all",
        "visual_intent": False,
        "execution_plan": [],
        "unknown_tickers": [],
        "retrieved_chunks": [],
        "retrieved_charts": [],
        "sql_results": [],
        "anomaly_scores": [],
        "generated_charts": [],
        "web_context": "",
        "web_sources": [],
        "conversation_history": conversation_history or [],
        "final_answer": "",
        "sources": [],
    }

    final_state: dict[str, Any] = {}
    step_index = 0
    node_start: float | None = None

    for chunk in agent_graph.stream(initial_state, stream_mode="updates"):
        # chunk is {node_name: state_update_dict}
        for node_name, state_update in chunk.items():
            if node_name == "__start__":
                node_start = time.time()
                continue

            # Measure duration: time from previous node_start (or stream start) to now
            now = time.time()
            started_at = node_start if node_start is not None else now
            duration_ms = int((now - started_at) * 1000)

            final_state.update(state_update)
            event = {
                "event": "step",
                "step": step_index,
                "node": node_name,
                "label": _NODE_LABELS.get(node_name, node_name),
                "detail": _extract_step_detail(node_name, state_update),
                "started_at": round(started_at, 3),
                "duration_ms": duration_ms,
            }
            yield f"data: {json.dumps(event)}\n\n"
            step_index += 1
            # Next node starts now
            node_start = time.time()

    # Emit final result
    result_payload = {
        "event": "result",
        "data": {
            "query": query,
            "query_type": final_state.get("query_type", "general"),
            "tickers": final_state.get("tickers", []),
            "final_answer": final_state.get("final_answer", ""),
            "sources": final_state.get("sources", []),
            "retrieved_charts": final_state.get("retrieved_charts", []),
            "anomaly_scores": final_state.get("anomaly_scores", []),
            "generated_charts": final_state.get("generated_charts", []),
            "web_sources": final_state.get("web_sources", []),
        },
    }
    yield f"data: {json.dumps(result_payload)}\n\n"
