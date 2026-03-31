"""Query router — /query endpoint for the SecSignal agent system."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from secsignal.agents.graph import run_query

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["query"])


class QueryRequest(BaseModel):
    """Request body for the /query endpoint."""

    query: str = Field(..., min_length=3, max_length=2000, description="Natural language query about SEC filings")
    tickers: list[str] | None = Field(default=None, description="Optional ticker filter (e.g. ['AAPL', 'MSFT'])")


class SourceCitation(BaseModel):
    """A source citation in the response."""

    ticker: str
    filing_date: str
    filing_type: str
    content_type: str


class ChartResult(BaseModel):
    """A chart image in the response."""

    image_id: str
    description: str
    ticker: str
    filing_date: str
    chart_type: str
    image_data_b64: str
    score: float


class AnomalyResult(BaseModel):
    """An anomaly flag in the response."""

    ticker: str
    metric: str
    filing_date: str
    value: float
    z_score: float
    direction: str


class QueryResponse(BaseModel):
    """Response body from the /query endpoint."""

    query: str
    query_type: str
    tickers: list[str]
    answer: str
    sources: list[dict[str, Any]]
    charts: list[dict[str, Any]]
    anomalies: list[dict[str, Any]]


@router.post("/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest) -> QueryResponse:
    """Run a natural language query through the SecSignal agent system.

    The query is classified, routed to a specialist agent (trend, comparison,
    or anomaly), and synthesized into a cited answer.
    """
    logger.info("query_received", query=request.query[:60], tickers=request.tickers)

    try:
        result = run_query(
            query=request.query,
            tickers=request.tickers,
        )
    except Exception:
        logger.exception("query_failed", query=request.query[:60])
        raise HTTPException(status_code=500, detail="Agent system error. Please try again.")

    return QueryResponse(
        query=result["query"],
        query_type=result["query_type"],
        tickers=result["tickers"],
        answer=result["final_answer"],
        sources=result["sources"],
        charts=[
            {k: v for k, v in c.items() if k != "image_data_b64"}
            for c in result.get("retrieved_charts", [])
        ],
        anomalies=result.get("anomaly_scores", []),
    )


@router.get("/charts/{image_id}")
async def get_chart_image(image_id: str) -> dict:
    """Retrieve a specific chart image by ID.

    Returns the base64-encoded image data separately to keep the main
    query response lightweight.
    """
    from secsignal.agents.tools.visual_tool import search_charts

    # Search for the specific image
    try:
        from secsignal.agents.connection import get_snowflake_connection

        conn = get_snowflake_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT fi.IMAGE_ID, fi.IMAGE_DATA_B64, fi.IMAGE_FORMAT,
                       ie.DESCRIPTION, ie.TICKER, ie.CHART_TYPE
                FROM SECSIGNAL.RAW.FILING_IMAGES fi
                LEFT JOIN SECSIGNAL.RAW.IMAGE_EMBEDDINGS ie ON fi.IMAGE_ID = ie.IMAGE_ID
                WHERE fi.IMAGE_ID = %s
                LIMIT 1
                """,
                (image_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"Chart {image_id} not found")

            columns = [desc[0] for desc in cursor.description]
            result = dict(zip(columns, row))
            return {
                "image_id": result["IMAGE_ID"],
                "image_data_b64": result["IMAGE_DATA_B64"],
                "image_format": result["IMAGE_FORMAT"],
                "description": result.get("DESCRIPTION"),
                "ticker": result.get("TICKER"),
                "chart_type": result.get("CHART_TYPE"),
            }
        finally:
            cursor.close()
    except HTTPException:
        raise
    except Exception:
        logger.exception("get_chart_failed", image_id=image_id)
        raise HTTPException(status_code=500, detail="Failed to retrieve chart image")
