"""LangGraph state schema for the SecSignal multi-agent system.

Defines the shared state that flows through supervisor → specialists → synthesizer.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

import operator
from typing_extensions import TypedDict


class RetrievedChunk(TypedDict):
    """A text chunk retrieved from Cortex Search or vector similarity."""

    content: str
    ticker: str
    filing_type: str
    filing_date: str
    content_type: str  # 'text_chunk' or 'chart_description'
    score: float


class RetrievedChart(TypedDict):
    """A chart image retrieved via cross-modal search."""

    image_id: str
    description: str
    ticker: str
    filing_type: str
    filing_date: str
    chart_type: str
    image_data_b64: str
    score: float


class AnomalyScore(TypedDict):
    """A flagged anomaly from z-score detection."""

    ticker: str
    metric: str
    filing_date: str
    value: float
    z_score: float
    direction: str  # 'increase' or 'decrease'


class FilingState(TypedDict):
    """Shared state for the SecSignal LangGraph agent system.

    Flows: supervisor → [trend|comparison|anomaly] → synthesizer
    """

    # Input
    query: str
    query_type: Literal["trend", "comparison", "anomaly", "general"]
    tickers: list[str]
    time_range: str  # e.g. "last 8 quarters", "2023-2024"
    visual_intent: bool  # whether user wants chart/graph results

    # Retrieved data (accumulated by specialist agents)
    retrieved_chunks: Annotated[list[RetrievedChunk], operator.add]
    retrieved_charts: Annotated[list[RetrievedChart], operator.add]
    sql_results: Annotated[list[dict[str, Any]], operator.add]
    anomaly_scores: Annotated[list[AnomalyScore], operator.add]
    generated_charts: Annotated[list[dict[str, Any]], operator.add]  # chart data for Streamlit rendering

    # Output
    final_answer: str
    sources: list[dict[str, str]]  # citation references
