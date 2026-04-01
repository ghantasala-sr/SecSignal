# SecSignal

Agentic RAG system for SEC financial intelligence. Analyze trends, compare companies, and detect anomalies across 10-K and 10-Q filings — powered by Snowflake Cortex.

## Architecture

```
SEC EDGAR ──▶ Ingestion ──▶ Snowflake (RAW → dbt → MARTS)
                                │
                          Cortex Search + Dual Embeddings
                                │
User Query ──▶ LangGraph Agents ──▶ FastAPI (SSE) ──▶ Next.js Frontend
```

A LangGraph supervisor classifies each query, routes to a specialist agent (trend, comparison, or anomaly), enriches with real-time web data via Cortex Agent, and synthesizes a final answer with charts, sources, and anomaly scores.

See the in-app [Architecture page](/architecture) for detailed diagrams, data lineage, and design pattern documentation.

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Data Warehouse | Snowflake | Storage, compute, Cortex AI functions |
| LLM | Cortex COMPLETE (claude-sonnet-4-6) | Classification, synthesis, chart extraction |
| Search | Cortex Search (SEARCH_PREVIEW) | Semantic retrieval over filing sections |
| Web Search | Cortex Agent (AGENT_RUN) | Real-time market data and news |
| Embeddings | Arctic embed + Voyage multimodal-3 | Text and cross-modal embeddings (1024d) |
| Doc Parsing | Cortex AI_PARSE_DOCUMENT | PDF layout extraction with images |
| Agent Framework | LangGraph (StateGraph) | Multi-agent orchestration with shared state |
| Transforms | dbt | SQL-based staging → intermediate → marts pipeline |
| Orchestration | Apache Airflow | Weekly DAG scheduling |
| API | FastAPI | REST + SSE streaming endpoints |
| Frontend | Next.js 16 (App Router) | React UI with shadcn/ui, recharts, react-markdown |

## Project Structure

```
SecSignal/
├── secsignal/
│   ├── agents/                  # LangGraph agent system
│   │   ├── graph.py             # StateGraph definition + run_query / run_query_stream
│   │   ├── state.py             # FilingState TypedDict
│   │   ├── supervisor.py        # Query classifier + conditional router
│   │   ├── trend_agent.py       # Single-company time-series specialist
│   │   ├── comparison_agent.py  # Multi-company comparison specialist
│   │   ├── anomaly_agent.py     # Z-score anomaly detection specialist
│   │   ├── web_search_agent.py  # Cortex Agent web search + chart extraction
│   │   ├── synthesizer.py       # Final answer synthesis
│   │   ├── connection.py        # Snowflake connection management
│   │   └── tools/               # Agent tools
│   │       ├── semantic_tool.py     # Cortex Search (SEARCH_PREVIEW)
│   │       ├── chart_generator.py   # Chart data from EXTRACTED_FINANCIALS
│   │       ├── web_search_tool.py   # Cortex Agent web search + TTL cache
│   │       ├── anomaly_scorer.py    # Z-score anomaly detection
│   │       ├── sql_tool.py          # Direct SQL queries
│   │       └── visual_tool.py       # Image/chart retrieval
│   ├── ingestion/               # SEC EDGAR data ingestion
│   │   ├── edgar_client.py      # Async EFTS + Submissions API client
│   │   ├── filing_parser.py     # Section-aware HTML parser + chunker
│   │   └── gcs_uploader.py      # Cloud storage uploads
│   ├── processing/              # Document processing
│   │   ├── document_parser.py   # AI_PARSE_DOCUMENT wrapper
│   │   ├── image_extractor.py   # Image extraction from filings
│   │   ├── chart_analyzer.py    # Chart OCR and analysis
│   │   └── description_gen.py   # Image description generation
│   ├── embeddings/              # Embedding pipeline
│   │   ├── cortex_embed.py      # Dual embedding orchestrator
│   │   ├── text_embedder.py     # Arctic embed (text-to-text)
│   │   └── image_embedder.py    # Voyage multimodal-3 (cross-modal)
│   ├── api/                     # FastAPI backend
│   │   ├── main.py              # App setup, CORS, middleware
│   │   ├── routers/query.py     # /api/query + /api/query/stream endpoints
│   │   └── middleware/tracing.py
│   ├── airflow/
│   │   └── dags/ingest_filings.py  # Weekly 6-task DAG
│   └── frontend/                # Next.js 16 app
│       ├── app/
│       │   ├── page.tsx             # Home (chat interface)
│       │   ├── architecture/page.tsx # Architecture documentation
│       │   ├── layout.tsx           # Root layout + NavHeader
│       │   └── globals.css          # Dark theme (oklch colors)
│       ├── components/
│       │   ├── nav-header.tsx       # Shared navigation
│       │   ├── query-input.tsx      # Search input
│       │   ├── thread-message.tsx   # Message bubble + trajectory
│       │   ├── analysis-result.tsx  # Full result rendering
│       │   ├── analysis-skeleton.tsx # Loading skeleton
│       │   ├── chart-panel.tsx      # recharts rendering
│       │   ├── source-list.tsx      # Filing source citations
│       │   ├── web-source-list.tsx  # Web source citations
│       │   └── anomaly-card.tsx     # Anomaly score display
│       ├── lib/
│       │   ├── api.ts               # Types + API client
│       │   └── use-query-stream.ts  # SSE streaming hook
│       └── next.config.ts           # API proxy to FastAPI :8000
├── dbt/                         # dbt project
│   ├── dbt_project.yml
│   ├── profiles.yml
│   └── models/
│       ├── staging/             # stg_companies, stg_filings, stg_sections, ...
│       ├── intermediate/        # int_parsed_sections, int_chart_extracts
│       └── marts/               # fct_risk_factors, fct_financials, fct_chart_data, dim_filing_images
├── sql/                         # Snowflake DDL scripts (00-06)
├── scripts/                     # Pipeline runner + test scripts
├── tests/
├── k8s/                         # Kubernetes manifests
├── observability/               # Monitoring configuration
└── pyproject.toml
```

## Setup

### Environment Variables

Create a `.env` file in the project root:

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

Run the SQL scripts in order to create the database, stages, and tables:

```bash
# Execute DDL scripts 00 through 06
for f in sql/0*.sql; do snowsql -f "$f"; done
```

### dbt

```bash
cd dbt
dbt deps
dbt run     # staging → intermediate → marts
dbt test    # run schema + data tests
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
npm run build   # production build
```

## Snowflake Objects

### Tables (RAW schema)

| Table | Description |
|-------|-------------|
| RAW_COMPANIES | Company metadata (CIK, name, ticker, SIC code) |
| RAW_FILINGS | Filing metadata (accession number, form type, date) |
| RAW_FILING_SECTIONS | Parsed section text (Items 1, 1A, 7, 7A, 8) |
| FILING_IMAGES | Extracted images from filings |
| CHART_EXTRACTS | Chart OCR results (type, title, data points) |
| TEXT_EMBEDDINGS | Arctic embed vectors (1024d) |
| IMAGE_EMBEDDINGS | Voyage multimodal-3 vectors (1024d) |
| SEARCH_CORPUS | Cortex Search indexed documents |
| EXTRACTED_FINANCIALS | Structured financial metrics |

### dbt Marts

| Model | Description |
|-------|-------------|
| fct_risk_factors | Risk factor text by company, filing, and period |
| fct_financials | Extracted financial metrics (revenue, net income, etc.) |
| fct_chart_data | Chart data points with filing attribution |
| dim_filing_images | Image metadata dimension table |

### Cortex Services

| Service | Type | Description |
|---------|------|-------------|
| FILING_SEARCH_SERVICE | Cortex Search | Semantic retrieval over filing sections |
| SECSIGNAL_WEB_AGENT | Cortex Agent | Web search tool for real-time market data |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/query` | Synchronous query with full result |
| POST | `/api/query/stream` | SSE streaming with trajectory + result events |

### Request Body

```json
{
  "query": "How have Apple's risk factors changed over the last 3 years?",
  "conversation_history": []
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| query | string | Original query |
| query_type | string | Classification (trend, comparison, anomaly) |
| tickers | string[] | Extracted company tickers |
| answer | string | Markdown-formatted answer |
| sources | object[] | Filing section citations |
| charts | object[] | Retrieved chart data |
| anomalies | object[] | Z-score anomaly scores |
| generated_charts | object[] | LLM-extracted chart data from web context |
| web_sources | object[] | Web search citations |

## Data Pipeline

```
Weekly Airflow DAG:

fetch_metadata ──▶ process_filings ──┬──▶ process_images ──▶ embed_images
                                     └──▶ run_dbt ──────────▶ embed_text
```

1. **fetch_metadata** — Query EDGAR EFTS + Submissions APIs for new filings
2. **process_filings** — Parse HTML sections, chunk text, store in RAW tables
3. **process_images** — Extract images via AI_PARSE_DOCUMENT, analyze charts
4. **run_dbt** — Transform RAW → staging → intermediate → marts
5. **embed_images** — Generate Voyage multimodal-3 vectors for chart descriptions
6. **embed_text** — Generate Arctic embed vectors, update Cortex Search corpus
