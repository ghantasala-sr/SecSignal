"""SecSignal FastAPI application — agent-powered SEC filing intelligence API."""

from __future__ import annotations

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from secsignal.api.middleware.tracing import TracingMiddleware
from secsignal.api.routers.query import router as query_router

logger = structlog.get_logger(__name__)

app = FastAPI(
    title="SecSignal",
    description="Agentic RAG system for SEC financial intelligence",
    version="0.2.0",
)

# CORS — allow Streamlit frontend and local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request tracing
app.add_middleware(TracingMiddleware)

# Mount routers
app.include_router(query_router)


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "ok", "service": "secsignal", "version": "0.2.0"}


@app.get("/")
async def root() -> dict:
    """Root endpoint with API info."""
    return {
        "service": "SecSignal",
        "description": "Agentic RAG for SEC financial intelligence",
        "docs": "/docs",
        "endpoints": {
            "query": "POST /api/query",
            "chart": "GET /api/charts/{image_id}",
            "health": "GET /health",
        },
    }
