# SecSignal

**Agentic RAG system for SEC financial intelligence.** Analyze trends, compare companies, and detect anomalies across 10-K and 10-Q filings — powered by Snowflake Cortex AI, LangGraph multi-agent orchestration, and a real-time streaming UI.

SecSignal ingests SEC EDGAR filings for major companies (AAPL, AMZN, GOOGL, MSFT, NVDA, TSLA), transforms them into a queryable financial knowledge base on Snowflake, and serves answers through a multi-agent system that combines structured SQL queries, semantic search over filing text, web search for real-time data, and dynamic chart generation.

---

## Key Features

- **Multi-agent orchestration** — LangGraph supervisor classifies queries and fans out to 8 specialist agents (trend, comparison, anomaly, general, web search, valuation, sentiment, peer group) in parallel
- **Real-time streaming** — Server-Sent Events stream agent execution trajectory step-by-step as agents work
- **Dynamic chart generation** — Revenue trends, margin comparisons, risk distributions, radar profiles, and more rendered as interactive Recharts visualizations
- **Valuation analysis** — P/E ratios, gross/operating margins, growth-implied multiples, and basic DCF estimates from filing financials
- **Sentiment & tone analysis** — Scores MD&A and risk factor sections for bullish/neutral/bearish tone shifts across filings
- **Peer group comparison** — Benchmarks companies against sector peers with LLM-driven peer identification and multi-metric radar charts
- **Semantic search** — Cortex Search over 1,189 filing text chunks with ticker/date filtering
- **Web search fallback** — Unknown tickers automatically trigger Cortex Agent web search, with results clearly attributed
- **Input guardrails** — LLM-based pre-flight check rejects off-topic queries, prompt injection attempts, and gibberish before agents execute
- **Anomaly detection** — Z-score based anomaly scoring flags unusual financial metric changes
- **Follow-up suggestions** — LLM-generated follow-up questions after each answer to guide deeper exploration
- **Confidence scoring** — Weighted confidence score (source coverage, relevance quality, data richness) displayed per answer
- **Ticker autocomplete** — Client-side ticker matching with keyboard navigation in the query input
- **PDF export** — One-click export of analysis results (answer, charts, anomalies) to a print-friendly PDF
- **Portfolio watchlist** — localStorage-backed watchlist with per-ticker quick-query buttons and bulk comparison
- **Conversation memory** — Multi-turn chat with context summarization for follow-up questions
- **Evaluation framework** — Automated scoring of answer quality, source attribution, and chart relevance

---

## AI Architecture

```
                            ┌─────────────────────────────────────────┐
                            │            NEXT.JS FRONTEND             │
                            │   Chat UI + Recharts + SSE Streaming    │
                            └────────────────┬────────────────────────┘
                                             │ POST /api/query/stream
                                             ▼
                            ┌─────────────────────────────────────────┐
                            │            FASTAPI BACKEND              │
                            │  Rate Limiting ──▶ Input Guardrails     │
                            │  (slowapi 10/min)  (Cortex COMPLETE)    │
                            └────────────────┬────────────────────────┘
                                             │
                     ┌───────────────────────┼───────────────────────┐
                     │               LANGGRAPH ENGINE                │
                     │                                               │
                     │   ┌──────────────────────────────────┐        │
                     │   │        CLASSIFY_QUERY            │        │
                     │   │  Cortex COMPLETE (claude-sonnet)  │        │
                     │   │  • Extract tickers & time range  │        │
                     │   │  • Classify: trend/comparison/   │        │
                     │   │    anomaly/general/valuation/    │        │
                     │   │    sentiment/peer_group          │        │
                     │   │  • Validate tickers against DB   │        │
                     │   │  • Build execution plan          │        │
                     │   └──────────────┬───────────────────┘        │
                     │                  │                             │
                     │                  ▼                             │
                     │   ┌──────────────────────────────────┐        │
                     │   │          ROUTE_PLAN              │        │
                     │   │  LangGraph Send() fan-out        │        │
                     │   │  Parallel agent dispatch          │        │
                     │   └──┬────┬────┬────┬────┬────┬────┬────┬──┘    │
                     │      │    │    │    │    │    │    │    │        │
                     │      ▼    ▼    ▼    ▼    ▼    ▼    ▼    ▼        │
                     │   ┌────┐┌────┐┌────┐┌────┐┌────┐┌────┐┌────┐┌────┐│
                     │   │TRND││COMP││ANOM││GENL││ WEB││ VAL││SENT││PEER││
                     │   │AGNT││AGNT││AGNT││AGNT││AGNT││AGNT││AGNT││AGNT││
                     │   └──┬─┘└──┬─┘└──┬─┘└──┬─┘└──┬─┘└──┬─┘└──┬─┘└──┬─┘│
                     │      │     │     │     │     │     │     │     │  │
                     │      └─────┴─────┴─────┴──┬──┴─────┴─────┴─────┘  │
                     │                (results merge via operator.add)    │
                     │                           ▼                        │
                     │   ┌──────────────────────────────────┐            │
                     │   │          SYNTHESIZER             │            │
                     │   │  Cortex COMPLETE (claude-sonnet)  │            │
                     │   │  • Merge all agent results       │            │
                     │   │  • Generate cited markdown       │            │
                     │   │  • Extract chart data for UI     │            │
                     │   │  • Confidence scoring            │            │
                     │   │  • Follow-up question generation │            │
                     │   │  • Flag unknown tickers          │            │
                     │   └──────────────────────────────────┘            │
                     └───────────────────────────────────────────────┘
```

### Agent Details

| Agent | Responsibility | Tools Used |
|-------|---------------|------------|
| **Supervisor** | Query classification, ticker extraction, execution plan creation, ticker validation against filing DB | Cortex COMPLETE, direct SQL |
| **Trend Agent** | Single-company time-series analysis (revenue growth, margin trends, cash flow) | SQL Tool, Semantic Tool, Chart Generator |
| **Comparison Agent** | Multi-company side-by-side comparison (metrics, risk factors, competitive positioning) | SQL Tool, Semantic Tool, Chart Generator |
| **Anomaly Agent** | Statistical anomaly detection using z-scores over rolling windows | SQL Tool, Anomaly Scorer, Chart Generator |
| **General Agent** | Open-ended financial questions that don't fit other agent patterns | Semantic Tool, SQL Tool |
| **Web Search Agent** | Real-time market data, news, and coverage for unknown tickers or current events | Cortex Agent (AGENT_RUN), Chart Generator |
| **Valuation Agent** | P/E ratios, gross/operating margins, growth-implied multiples, basic DCF estimates | SQL Tool, Semantic Tool, Chart Generator |
| **Sentiment Agent** | MD&A and risk factor tone analysis, bullish/neutral/bearish scoring across filings | Semantic Tool, Cortex COMPLETE |
| **Peer Group Agent** | Sector peer identification, multi-metric benchmarking with radar charts | SQL Tool, Semantic Tool, Chart Generator |
| **Synthesizer** | Merges all agent outputs into a single cited answer with charts, confidence scoring, and follow-up question generation | Cortex COMPLETE |

### Snowflake Cortex AI Functions Used

| Function | Purpose |
|----------|---------|
| `SNOWFLAKE.CORTEX.COMPLETE()` | LLM calls — query classification, agent reasoning, answer synthesis, guardrail checks |
| `SNOWFLAKE.CORTEX.SEARCH_PREVIEW()` | Semantic search over 1,189 filing text chunks in Cortex Search service |
| `SNOWFLAKE.CORTEX.AGENT_RUN()` | Web search via Cortex Agent for real-time market data |
| `SNOWFLAKE.CORTEX.EMBED_TEXT_1024()` | Text embeddings (Arctic embed) and cross-modal embeddings (Voyage multimodal-3) |
| `SNOWFLAKE.CORTEX.AI_EXTRACT()` | Structured data extraction from filing charts |
| `SNOWFLAKE.CORTEX.AI_PARSE_DOCUMENT()` | PDF layout extraction with image preservation |

### How a Query Flows

1. **User submits**: "Compare NVDA and MSFT revenue growth over the last 3 years"
2. **Guardrails**: LLM classifies as finance-related — allowed through
3. **Classifier**: Extracts tickers `[NVDA, MSFT]`, classifies as `comparison`, builds plan `[comparison_agent]`
4. **Ticker validation**: Both found in DB — no web fallback needed
5. **Route & fan-out**: `Send("comparison_agent", state)` dispatches the comparison agent
6. **Comparison agent**: Queries `FCT_FINANCIALS` for revenue data, calls Cortex Search for relevant filing text, generates chart data (area chart, bar chart)
7. **Synthesizer**: Merges SQL results + semantic context + chart data, calls Cortex COMPLETE to produce a cited markdown answer with inline chart specifications
8. **Frontend**: Receives SSE events for each step (with timing), then the final result with interactive Recharts visualizations and collapsible source citations

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Data Warehouse | Snowflake | Storage, compute, Cortex AI functions |
| LLM | Cortex COMPLETE (claude-sonnet-4-6) | Classification, synthesis, guardrails |
| Search | Cortex Search (SEARCH_PREVIEW) | Semantic retrieval over filing sections |
| Web Search | Cortex Agent (AGENT_RUN) | Real-time market data and news |
| Embeddings | Arctic embed + Voyage multimodal-3 | Text and cross-modal embeddings (1024d) |
| Agent Framework | LangGraph (StateGraph + Send) | Multi-agent orchestration with parallel fan-out |
| Transforms | dbt | SQL-based staging → intermediate → marts pipeline |
| Orchestration | Apache Airflow | Weekly ingestion DAG scheduling |
| API | FastAPI + SSE | REST and streaming endpoints with rate limiting |
| Frontend | Next.js 16 (App Router) | React UI with shadcn/ui, Recharts, react-markdown |
| Security | slowapi + LLM guardrails | Rate limiting (10 req/min/IP) + input validation |

---

## Project Structure

```
SecSignal/
├── secsignal/
│   ├── agents/                     # LangGraph multi-agent system
│   │   ├── graph.py                # StateGraph definition + run_query / run_query_stream
│   │   ├── state.py                # FilingState TypedDict (shared agent state)
│   │   ├── supervisor.py           # Query classifier + ticker validator + router
│   │   ├── trend_agent.py          # Single-company time-series specialist
│   │   ├── comparison_agent.py     # Multi-company comparison specialist
│   │   ├── anomaly_agent.py        # Z-score anomaly detection specialist
│   │   ├── general_agent.py        # Open-ended financial Q&A specialist
│   │   ├── web_search_agent.py     # Cortex Agent web search + chart extraction
│   │   ├── valuation_agent.py      # P/E, margins, DCF valuation analysis
│   │   ├── sentiment_agent.py      # MD&A tone and sentiment scoring
│   │   ├── peer_group_agent.py     # Sector peer comparison with radar charts
│   │   ├── synthesizer.py          # Final answer synthesis with citations, confidence scores, follow-ups
│   │   ├── guardrails.py           # LLM-based input validation (pre-graph)
│   │   ├── connection.py           # Thread-safe Snowflake connection singleton
│   │   └── tools/                  # Shared agent tools
│   │       ├── semantic_tool.py    # Cortex Search (SEARCH_PREVIEW)
│   │       ├── chart_generator.py  # Dynamic chart data from financial tables
│   │       ├── web_search_tool.py  # Cortex Agent web search + TTL cache
│   │       ├── anomaly_scorer.py   # Z-score anomaly detection
│   │       ├── sql_tool.py         # Direct SQL queries against marts
│   │       └── visual_tool.py      # Image/chart retrieval
│   │
│   ├── evaluation/                 # Evaluation framework
│   │   ├── runner.py               # End-to-end eval runner
│   │   ├── scorers.py              # LLM-as-judge + heuristic scorers
│   │   └── test_cases.py           # Curated test suite
│   │
│   ├── ingestion/                  # SEC EDGAR data ingestion
│   │   ├── edgar_client.py         # Async EFTS + Submissions API client
│   │   ├── filing_parser.py        # Section-aware HTML parser + chunker
│   │   └── gcs_uploader.py         # Cloud storage uploads
│   │
│   ├── processing/                 # Document processing
│   │   ├── document_parser.py      # AI_PARSE_DOCUMENT wrapper
│   │   ├── image_extractor.py      # Image extraction from filings
│   │   ├── chart_analyzer.py       # Chart OCR and analysis
│   │   └── description_gen.py      # Image description generation
│   │
│   ├── embeddings/                 # Embedding pipeline
│   │   ├── cortex_embed.py         # Dual embedding orchestrator
│   │   ├── text_embedder.py        # Arctic embed (text-to-text, 1024d)
│   │   └── image_embedder.py       # Voyage multimodal-3 (cross-modal, 1024d)
│   │
│   ├── api/                        # FastAPI backend
│   │   ├── main.py                 # App setup, CORS, rate limiting, middleware
│   │   ├── routers/query.py        # /api/query + /api/query/stream endpoints
│   │   └── middleware/tracing.py    # OpenTelemetry instrumentation
│   │
│   ├── airflow/
│   │   └── dags/ingest_filings.py  # Weekly 6-task ingestion DAG
│   │
│   └── frontend/                   # Next.js 16 application
│       ├── app/
│       │   ├── page.tsx            # Home (chat interface)
│       │   ├── architecture/       # Architecture documentation page
│       │   └── layout.tsx          # Root layout + navigation
│       ├── components/
│       │   ├── query-input.tsx     # Search input with ticker autocomplete + keyboard nav
│       │   ├── thread-message.tsx  # Message bubble + agent trajectory
│       │   ├── analysis-result.tsx # Full result with sources, PDF export, follow-ups
│       │   ├── chart-panel.tsx     # Recharts rendering (area, bar, pie, radar, composed)
│       │   ├── anomaly-card.tsx    # Anomaly score display
│       │   ├── source-list.tsx     # Filing source citations
│       │   ├── web-source-list.tsx # Web source citations with links
│       │   └── watchlist.tsx       # Portfolio watchlist with quick-query buttons
│       └── lib/
│           ├── api.ts              # Types + API client
│           └── use-query-stream.ts # SSE streaming hook with conversation memory
│
├── dbt/                            # dbt project (staging → intermediate → marts)
├── sql/                            # Snowflake DDL scripts (00-06)
├── scripts/                        # Pipeline runner + evaluation scripts
├── tests/                          # Test suite
├── Dockerfile                      # Backend container for deployment
├── .dockerignore                   # Excludes secrets, frontend, test files
├── pyproject.toml                  # Python dependencies + tool config
└── .env.example                    # Environment variable template
```

---

## Data Pipeline

```
SEC EDGAR (EFTS API)
    │  Weekly Airflow DAG
    ▼
GCS Bucket (raw HTML/XBRL)
    │
    ▼
Snowflake RAW Schema
    │
    ├──▶ dbt staging     (clean, type-cast, dedup)
    ├──▶ dbt intermediate (parsed sections, chart extracts)
    ├──▶ dbt marts        (fct_financials, fct_risk_factors, fct_chart_data)
    │
    ├──▶ Text Embeddings  (Arctic embed, 1024d vectors)
    ├──▶ Image Embeddings  (Voyage multimodal-3, cross-modal vectors)
    └──▶ Cortex Search     (1,189 indexed chunks for semantic retrieval)
```

### Snowflake Objects

**Tables (RAW schema)**

| Table | Description |
|-------|-------------|
| RAW_COMPANIES | Company metadata (CIK, name, ticker, SIC code) |
| RAW_FILINGS | Filing metadata (accession number, form type, date) |
| RAW_FILING_SECTIONS | Parsed section text (Items 1, 1A, 7, 7A, 8) |
| EXTRACTED_FINANCIALS | Structured financial metrics (revenue, net income, margins, etc.) |
| SEARCH_CORPUS | Cortex Search indexed documents (1,189 chunks) |
| FILING_IMAGES | Extracted images from filings |
| TEXT_EMBEDDINGS | Arctic embed vectors (1024d) |
| IMAGE_EMBEDDINGS | Voyage multimodal-3 vectors (1024d) |

**dbt Marts**

| Model | Description |
|-------|-------------|
| fct_risk_factors | Risk factor text by company, filing, and period (6 tickers, 11 rows) |
| fct_financials | Extracted financial metrics (5 tickers, 10 rows) |
| fct_chart_data | Chart data points with filing attribution (4 tickers, 10 rows) |

**Cortex Services**

| Service | Type | Description |
|---------|------|-------------|
| FILING_SEARCH_SERVICE | Cortex Search | Semantic retrieval over filing sections |
| SECSIGNAL_WEB_AGENT | Cortex Agent | Web search for real-time market data |

---

## Security & Production Hardening

| Feature | Implementation |
|---------|---------------|
| **Input guardrails** | LLM-based pre-graph classification rejects off-topic, injection, and gibberish |
| **Rate limiting** | slowapi — 10 requests/minute per IP |
| **CORS restriction** | `ALLOWED_ORIGINS` env var (no wildcard in production) |
| **Credential safety** | All Snowflake creds via env vars, never in code or Docker images |
| **Unknown ticker handling** | Auto-validates tickers against DB, falls back to web search, explicitly tells user |
| **Pydantic validation** | Query length 3-2000 chars, conversation history max 4000 chars/turn |

---

## Setup

### Environment Variables

Create a `.env` file from the template:

```bash
cp .env.example .env
# Edit .env with your Snowflake credentials
```

Required variables:
```env
SNOWFLAKE_ACCOUNT=<your_account>
SNOWFLAKE_USER=<your_user>
SNOWFLAKE_PASSWORD=<your_password>
SNOWFLAKE_WAREHOUSE=<your_warehouse>
SNOWFLAKE_DATABASE=SECSIGNAL
SNOWFLAKE_ROLE=<your_role>
CORTEX_LLM_MODEL=claude-sonnet-4-6
```

### Snowflake Setup

Run the DDL scripts in order:
```bash
for f in sql/0*.sql; do snowsql -f "$f"; done
```

### dbt

```bash
cd dbt
dbt deps
dbt run     # staging → intermediate → marts
dbt test
```

### Backend

```bash
pip install -e .
uvicorn secsignal.api.main:app --port 8000
```

### Frontend

```bash
cd secsignal/frontend
npm install
npm run dev     # development at localhost:3000
```

---

## Deployment

The project is configured for deployment with **Vercel** (frontend) + **Render** (backend).

### Backend (Render)

1. Connect GitHub repo to Render as a new Web Service
2. Render auto-detects the `Dockerfile`
3. Set environment variables in Render dashboard (Snowflake creds, `ALLOWED_ORIGINS`)
4. Health check path: `/health`

### Frontend (Vercel)

1. Import repo into Vercel, set root directory to `secsignal/frontend`
2. Set `NEXT_PUBLIC_STREAM_URL` to your Render backend URL
3. Deploy

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/query` | Synchronous query with full result |
| POST | `/api/query/stream` | SSE streaming with agent trajectory + result events |
| POST | `/api/summarize` | Condense long answers for conversation context |
| GET | `/api/charts/{image_id}` | Retrieve specific chart image |
| GET | `/health` | Health check |

### Request

```json
{
  "query": "Compare NVDA and MSFT revenue growth over the last 3 years",
  "tickers": ["NVDA", "MSFT"],
  "context": []
}
```

### Response

| Field | Type | Description |
|-------|------|-------------|
| query | string | Original query |
| query_type | string | Classification (trend, comparison, anomaly, general, valuation, sentiment, peer_group) |
| tickers | string[] | Extracted company tickers |
| answer | string | Markdown-formatted cited answer |
| sources | object[] | Filing section citations |
| generated_charts | object[] | Chart data for Recharts rendering |
| anomalies | object[] | Z-score anomaly flags |
| web_sources | object[] | Web search citations |
| follow_up_questions | string[] | LLM-generated follow-up question suggestions |
| confidence_score | number | Weighted confidence score (0–1) for the answer |
| confidence_factors | object | Breakdown: source_coverage, relevance_quality, data_richness |

### SSE Events (streaming endpoint)

| Event | Description |
|-------|-------------|
| `step` | Agent execution step with node name, label, timing, and details |
| `result` | Final complete result payload |
| `error` | Execution error |
| `guardrail_rejected` | Input rejected by guardrails (with reason) |

---

## Sample Queries

| Type | Query |
|------|-------|
| **Trend** | "How has NVDA's revenue grown over the last 3 years?" |
| **Comparison** | "Compare AAPL and MSFT operating margins and R&D spending" |
| **Anomaly** | "Flag any unusual changes in TSLA's risk factors between filings" |
| **Valuation** | "What is MSFT's P/E ratio and how do its margins compare to historical averages?" |
| **Sentiment** | "Analyze the tone of NVDA's latest MD&A — is management bullish or cautious?" |
| **Peer Group** | "How does AMZN stack up against its sector peers on revenue growth and margins?" |
| **General** | "What are the key risk factors for cloud computing companies?" |
| **Cross-company** | "Which company has better free cash flow generation — AMZN or GOOGL?" |
| **Unknown ticker** | "How does AMD compare to NVDA in the GPU market?" (triggers web fallback for AMD) |
| **Complex** | "Build a risk matrix for NVDA, GOOGL, and MSFT — cross-reference risk factors with financial performance and tell me which carries the highest downside risk" |

---

## Evaluation

Run the evaluation suite to score answer quality:

```bash
python scripts/run_evaluation.py
```

Evaluation dimensions: answer relevance, source attribution, chart appropriateness, factual accuracy (LLM-as-judge + heuristic scorers).
