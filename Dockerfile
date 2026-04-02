# ---------- SecSignal FastAPI Backend ----------
# Multi-stage build: install deps first (cached), then copy app code.

FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps needed by snowflake-connector-python (pyarrow, openssl)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ libssl-dev && \
    rm -rf /var/lib/apt/lists/*

# ---------- Dependencies ----------
FROM base AS deps

COPY pyproject.toml ./
# Install the project in editable mode so secsignal package is importable
COPY . .
RUN pip install --no-cache-dir -e ".[dev]"

# ---------- Runtime ----------
FROM deps AS runtime

# Render injects PORT env var; default to 8000 for local testing
ENV PORT=8000

EXPOSE ${PORT}

# Run uvicorn — bind to 0.0.0.0 so the container is reachable
CMD ["sh", "-c", "uvicorn secsignal.api.main:app --host 0.0.0.0 --port ${PORT}"]
