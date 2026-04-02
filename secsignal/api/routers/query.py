"""Query router — /query endpoint for the SecSignal agent system."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from secsignal.agents.graph import run_query, run_query_stream
from secsignal.agents.connection import get_snowflake_connection
from secsignal.agents.guardrails import check_input_guardrails

logger = structlog.get_logger(__name__)

LLM_MODEL = os.environ.get("CORTEX_LLM_MODEL", "claude-sonnet-4-6")

router = APIRouter(prefix="/api", tags=["query"])

limiter = Limiter(key_func=get_remote_address)


class ConversationTurn(BaseModel):
    """A single turn in the conversation history."""

    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., max_length=4000)


class QueryRequest(BaseModel):
    """Request body for the /query endpoint."""

    query: str = Field(..., min_length=3, max_length=2000, description="Natural language query about SEC filings")
    tickers: list[str] | None = Field(default=None, description="Optional ticker filter (e.g. ['AAPL', 'MSFT'])")
    context: list[ConversationTurn] | None = Field(default=None, description="Recent conversation history for follow-up questions")


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
    generated_charts: list[dict[str, Any]]
    web_sources: list[dict[str, Any]]


@router.post("/query", response_model=QueryResponse)
@limiter.limit("10/minute")
async def query_endpoint(request: Request, body: QueryRequest) -> QueryResponse:
    """Run a natural language query through the SecSignal agent system.

    The query is classified, routed to a specialist agent (trend, comparison,
    or anomaly), and synthesized into a cited answer.
    """
    logger.info("query_received", query=body.query[:60], tickers=body.tickers)

    # --- Input guardrails: reject off-topic / injection / gibberish ---
    guardrail = check_input_guardrails(body.query)
    if not guardrail["allowed"]:
        raise HTTPException(status_code=422, detail=guardrail.get("reason", "Query not allowed."))
    # --- End input guardrails ---

    history = [{"role": t.role, "content": t.content} for t in (body.context or [])]

    try:
        result = run_query(
            query=body.query,
            tickers=body.tickers,
            conversation_history=history or None,
        )
    except Exception:
        logger.exception("query_failed", query=body.query[:60])
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
        generated_charts=result.get("generated_charts", []),
        web_sources=result.get("web_sources", []),
    )


@router.post("/query/stream")
@limiter.limit("10/minute")
async def query_stream_endpoint(request: Request, body: QueryRequest) -> StreamingResponse:
    """Stream query execution with real-time agent trajectory events.

    Returns a Server-Sent Events stream. Each event is a JSON object:
      - {"event": "step", "step": 0, "node": "classify_query", "label": "...", "detail": {...}}
      - {"event": "result", "data": { ...full QueryResponse payload... }}

    Uses an async generator that runs the sync graph stream in a thread
    pool, yielding SSE events one at a time without buffering.
    """
    logger.info("query_stream_received", query=body.query[:60], tickers=body.tickers)

    # --- Input guardrails: reject off-topic / injection / gibberish ---
    guardrail = check_input_guardrails(body.query)
    if not guardrail["allowed"]:
        reason = guardrail.get("reason", "Query not allowed.")
        logger.info("guardrail_stream_rejected", query=body.query[:60], reason=reason)

        async def rejection_generator():
            error_event = {"event": "guardrail_rejected", "message": reason}
            yield f"data: {json.dumps(error_event)}\n\n"

        return StreamingResponse(
            rejection_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )
    # --- End input guardrails ---

    history = [{"role": t.role, "content": t.content} for t in (body.context or [])]

    async def event_generator():
        """Async generator — runs sync graph in thread, yields SSE events."""
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        def _run_sync():
            """Execute the sync generator and push events into the async queue."""
            try:
                for sse_event in run_query_stream(
                    query=body.query,
                    tickers=body.tickers,
                    conversation_history=history or None,
                ):
                    loop.call_soon_threadsafe(queue.put_nowait, sse_event)
            except Exception:
                logger.exception("query_stream_failed", query=body.query[:60])
                error_event = {"event": "error", "message": "Agent system error. Please try again."}
                loop.call_soon_threadsafe(
                    queue.put_nowait, f"data: {json.dumps(error_event)}\n\n"
                )
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        # Start the sync generator in a background thread
        asyncio.ensure_future(loop.run_in_executor(None, _run_sync))

        # Yield events as they arrive
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
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


class SummarizeRequest(BaseModel):
    """Request body for the /summarize endpoint."""

    text: str = Field(..., min_length=10, max_length=20000)


class SummarizeResponse(BaseModel):
    """Response body from the /summarize endpoint."""

    summary: str


SUMMARIZE_PROMPT = """Condense the following financial analysis into a brief summary (max 3-4 sentences). Preserve the key tickers, metrics, findings, and any numbers. Drop formatting, section headers, and hedging language. Output ONLY the summary, no preamble.

Text:
{text}"""


@router.post("/summarize", response_model=SummarizeResponse)
async def summarize_endpoint(request: SummarizeRequest) -> SummarizeResponse:
    """Summarize a long analysis answer for use as conversation context."""
    conn = get_snowflake_connection()
    cursor = conn.cursor()
    try:
        prompt = SUMMARIZE_PROMPT.format(text=request.text[:12000])
        cursor.execute(
            "SELECT SNOWFLAKE.CORTEX.COMPLETE(%s, %s) AS response",
            (LLM_MODEL, prompt),
        )
        row = cursor.fetchone()
        summary = row[0] if row else request.text[:500]
        return SummarizeResponse(summary=summary.strip())
    except Exception:
        logger.exception("summarize_failed")
        # Fallback: return truncated text rather than failing the follow-up
        return SummarizeResponse(summary=request.text[:500])
    finally:
        cursor.close()
