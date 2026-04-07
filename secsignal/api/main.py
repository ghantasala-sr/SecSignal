"""SecSignal FastAPI application — agent-powered SEC filing intelligence API."""

from __future__ import annotations

import os

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from secsignal.api.middleware.tracing import TracingMiddleware
from secsignal.api.routers.query import router as query_router

logger = structlog.get_logger(__name__)

# Access code gate — if set, requests to /api/query* must include a matching
# X-Access-Code header.  Leave unset to disable the gate entirely.
ACCESS_CODE = os.environ.get("SECSIGNAL_ACCESS_CODE", "")

# Paths that are protected by the access code gate
_PROTECTED_PREFIXES = ("/api/query",)


class AccessCodeMiddleware(BaseHTTPMiddleware):
    """Reject requests to protected endpoints that lack a valid access code."""

    async def dispatch(self, request: Request, call_next):
        # Skip preflight OPTIONS requests (CORS) and non-protected paths
        if request.method == "OPTIONS":
            return await call_next(request)
        if ACCESS_CODE and any(request.url.path.startswith(p) for p in _PROTECTED_PREFIXES):
            code = request.headers.get("x-access-code", "")
            if code != ACCESS_CODE:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Access code required. Enter a valid access code to use SecSignal."},
                )
        return await call_next(request)


app = FastAPI(
    title="SecSignal",
    description="Agentic RAG system for SEC financial intelligence",
    version="0.2.0",
)

# Rate limiting — 5 queries/day per IP + 10/minute burst cap
limiter = Limiter(key_func=get_remote_address, default_limits=["10/minute"])
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Daily query limit (5) reached. Please try again tomorrow."},
    )

# CORS — restrict origins in production via ALLOWED_ORIGINS env var.
# Defaults to localhost for local dev. Set to your Vercel URL in production.
_raw_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000")
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Request tracing
app.add_middleware(TracingMiddleware)

# Access code gate (runs after CORS, so preflight OPTIONS still works)
app.add_middleware(AccessCodeMiddleware)

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
