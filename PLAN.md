# SecSignal

> Production-grade Agentic RAG system for SEC financial intelligence, built on Snowflake + GKE

---

## Overview

FillingTinker ingests SEC EDGAR filings (10-K, 10-Q, 8-K), transforms them into a queryable financial knowledge base on Snowflake, and serves answers through a multi-agent LangGraph system deployed on Google Kubernetes Engine. Users can ask natural language questions about individual companies, compare across companies, detect risk anomalies, and analyze financial trends over time.

---

## Goals

- Build a production-grade agentic RAG pipeline end-to-end
- Demonstrate MLOps depth: KServe, KEDA, GKE Autopilot, Airflow on Kubernetes
- Demonstrate Data Engineering depth: EDGAR ingestion, dbt, Snowflake Cortex AI
- Showcase multi-agent orchestration: LangGraph supervisor + specialist subagents
- Stay within GCP free tier throughout development

---

## Tech Stack

| Layer | Technology |
|---|---|
| Filing source | SEC EDGAR Full-Text Search API (EFTS — free, no API key) |
| Raw storage | GCS (Google Cloud Storage) |
| Data warehouse | Snowflake (RAW → staging → marts via dbt) |
| Document parsing | HTML `<img>` tag extraction + BeautifulSoup (EDGAR XHTML not supported by AI_PARSE_DOCUMENT) |
| Chart analysis | Snowflake Cortex `AI_EXTRACT` (vision-language model for structured chart data) |
| Text embeddings | Snowflake Cortex `EMBED_TEXT_1024` — `snowflake-arctic-embed-l-v2.0-8k` (1024 dims) |
| Image embeddings | Snowflake Cortex `EMBED_TEXT_1024` — `voyage-multimodal-3` (cross-modal text↔image, data URI) |
| Vector search | Snowflake Cortex Search |
| LLM generation | Snowflake Cortex LLM (managed, multimodal — Claude/LLaMA for chart analysis) |
| Agent framework | LangGraph (supervisor + specialist subagents) |
| Orchestration | Apache Airflow (Helm chart on GKE) |
| Model serving | KServe InferenceService (OSS embedding model) |
| Autoscaling | KEDA (queue-based) + GKE HPA |
| Cluster | GKE Autopilot (free tier) |
| Container registry | GCP Artifact Registry |
| API layer | FastAPI (Kubernetes Deployment) |
| Ingress | NGINX ingress controller |
| Observability | Cloud Monitoring + Grafana + OpenTelemetry |
| Frontend | Streamlit |

---

## Agent Architecture

```
User query
    │
    ▼
Supervisor agent          ← classifies query type + detects visual intent
    │
    ├──► Trend agent       ← time-series analysis across quarters
    ├──► Comparison agent  ← multi-company diff
    └──► Anomaly agent     ← risk flag detection (z-score)
              │
              ├──► SQL tool          (dbt marts → structured financials)
              ├──► Semantic tool     (Cortex Search → filing text retrieval)
              ├──► Visual tool       (voyage-multimodal-3 → chart/graph retrieval)
              └──► Anomaly scorer    (z-score over Snowflake time-series)
                        │
                        ▼
                  Synthesizer node  ← Cortex LLM (multimodal) → cited answer
                                     with text + chart/graph references
```

---

## Data Pipeline

```
SEC EDGAR API (EFTS — free, no API key)
    │  (daily Airflow DAG)
    ▼
GCS bucket                  ← raw filing store (HTML, XBRL, PDF)
    │
    ▼
Snowflake RAW schema        ← COPY INTO from GCS stage
    │
    ▼
dbt staging models          ← clean, type-cast, dedup
    │
    ▼
dbt marts                   ← fact_financials, dim_companies, etc.
    │
    ├──► HTML <img> extraction   ← BeautifulSoup parses EDGAR XHTML → images
    │         │
    │         ├──► Text chunks → EMBED_TEXT_1024 (arctic-embed-l-v2.0-8k, 1024d)
    │         │         │
    │         │         ▼
    │         │    text_embeddings table (VECTOR(FLOAT,1024))
    │         │
    │         └──► Extracted images → AI_EXTRACT (chart data)
    │                   │             + AI_COMPLETE (chart descriptions)
    │                   │
    │                   ▼
    │              EMBED_TEXT_1024 (voyage-multimodal-3, data URI) → image_embeddings table
    │
    ├──► Cortex Search      ← search service over text + chart descriptions
    │
    └──► Agent layer        ← LangGraph reads from marts + search + visual
              │
              ▼
         FastAPI → Streamlit (with inline chart display)
```
SEC EDGAR API
    │  (daily Airflow DAG)
    ▼
GCS bucket              ← raw filing store (HTML, XBRL, text)
    │
    ▼
Snowflake RAW_SCHEMA    ← parsed text + metadata tables
    │
    ├──► dbt staging     ← cleaning, normalisation
    ├──► dbt marts       ← revenue, EPS, debt ratios, risk factors
    └──► Cortex embed    ← Arctic embed → Cortex Search vector index
```

---

## Project Structure

```
secsignal/
├── ingestion/
│   ├── edgar_client.py          # EDGAR EFTS API wrapper (free, no key)
│   ├── filing_parser.py         # XBRL + HTML → structured text
│   └── gcs_uploader.py          # raw filing → GCS (HTML, PDF, XBRL)
│
├── processing/
│   ├── document_parser.py       # legacy (unused — EDGAR XHTML not supported by AI_PARSE_DOCUMENT)
│   ├── image_extractor.py       # HTML <img> tag extraction + EDGAR image download
│   ├── chart_analyzer.py        # AI_EXTRACT → structured chart data
│   └── description_gen.py       # AI_COMPLETE (multimodal) → chart descriptions
│
├── embeddings/
│   ├── cortex_embed.py          # dual embedding orchestrator
│   ├── text_embedder.py         # EMBED_TEXT_1024 with arctic-embed-l-v2.0-8k (1024d)
│   └── image_embedder.py        # EMBED_TEXT_1024 with voyage-multimodal-3 (cross-modal, data URI)
│
├── dbt/
│   ├── models/
│   │   ├── staging/             # stg_filings, stg_companies, stg_filing_images
│   │   ├── intermediate/        # int_parsed_sections, int_chart_extracts
│   │   └── marts/               # fct_financials, fct_risk_factors,
│   │                            # fct_chart_data, dim_filing_images
│   ├── dbt_project.yml
│   └── profiles.yml
│
├── agents/
│   ├── graph.py                 # LangGraph state graph definition
│   ├── supervisor.py            # query classifier + router (visual intent)
│   ├── trend_agent.py           # time-series specialist
│   ├── comparison_agent.py      # multi-company specialist
│   ├── anomaly_agent.py         # risk flag specialist
│   ├── synthesizer.py           # Cortex LLM (multimodal) response generator
│   └── tools/
│       ├── sql_tool.py          # dbt mart queries
│       ├── semantic_tool.py     # Cortex Search retrieval (text)
│       ├── visual_tool.py       # voyage-multimodal-3 chart/graph retrieval
│       └── anomaly_scorer.py    # z-score anomaly detection
│
├── api/
│   ├── main.py                  # FastAPI app
│   ├── routers/
│   │   └── query.py             # /query endpoint (text + image responses)
│   └── middleware/
│       └── tracing.py           # OpenTelemetry instrumentation
│
├── airflow/
│   └── dags/
│       ├── edgar_ingestion.py   # daily ingestion DAG
│       └── multimodal_processing.py  # image extraction + embedding DAG
│
├── sql/
│   ├── 00_setup_database.sql    # database, schemas, warehouses, roles
│   ├── 01_create_stages.sql     # internal + external stages (GCS, images)
│   ├── 02_raw_tables.sql        # raw_filings, raw_companies, raw_filing_sections
│   ├── 03_parsed_documents.sql  # parsed_sections, filing_images, chart_extracts
│   ├── 04_embedding_tables.sql  # text_embeddings (1024d), image_embeddings
│   └── 05_cortex_search.sql     # search service over text + chart descriptions
│
├── k8s/
│   ├── namespace.yaml
│   ├── fastapi-deployment.yaml
│   ├── fastapi-hpa.yaml
│   ├── kserve-inference.yaml
│   ├── keda-scaledobject.yaml
│   ├── ingress.yaml
│   └── airflow-values.yaml      # Helm values override
│
├── observability/
│   ├── grafana-dashboard.json
│   └── otel-collector.yaml
│
├── frontend/
│   └── app.py                   # Streamlit UI (inline chart display)
│
├── tests/
│   ├── test_agents.py
│   ├── test_tools.py
│   ├── test_ingestion.py
│   ├── test_processing.py       # document parsing + image extraction
│   └── test_embeddings.py       # dual embedding validation
│
├── Dockerfile
├── docker-compose.yml           # local dev
├── pyproject.toml               # project config + dependencies
├── .env.example                 # environment variable template
├── .gitignore
└── README.md
```

---

## 4-Week Execution Plan

### Week 1 — Data plane + multimodal processing

**Goal:** EDGAR → Snowflake pipeline live, dbt marts queryable, dual embeddings (text + image) ready, Cortex Search operational

| Task | Details |
|---|---|
| EDGAR client | Pull 10-K, 10-Q, 8-K via EDGAR EFTS API (free, no key); filter by ticker/CIK |
| Filing parser | Extract section-aware text: Item 1A (Risk Factors), MD&A, financial statements |
| GCS uploader | Store raw filings in `gs://secsignal-raw/` with date-partitioned paths (HTML, PDF, XBRL) |
| Snowflake setup | Database `SECSIGNAL`, schemas (RAW, STAGING, INTERMEDIATE, MARTS), warehouse, roles |
| RAW tables | `raw_filings`, `raw_companies`, `raw_filing_sections` via COPY INTO from GCS stage |
| Document parsing | HTML `<img>` tag extraction via BeautifulSoup (EDGAR XHTML not supported by AI_PARSE_DOCUMENT) |
| Image extraction | Download referenced images from EDGAR URLs → `filing_images` table (base64-encoded) |
| Chart analysis | `AI_EXTRACT` → structured data from charts; `AI_COMPLETE` (multimodal) → chart descriptions |
| Text embeddings | `EMBED_TEXT_1024` with `snowflake-arctic-embed-l-v2.0-8k` → `text_embeddings` (VECTOR(FLOAT,1024)) |
| Image embeddings | `EMBED_TEXT_1024` with `voyage-multimodal-3` (data URI) → `image_embeddings` (cross-modal vectors) |
| dbt staging models | `stg_filings`, `stg_companies`, `stg_sections`, `stg_filing_images` — clean + normalise |
| dbt mart models | `fct_financials`, `fct_risk_factors`, `fct_chart_data`, `dim_filing_images` |
| Cortex Search index | Create search service over text chunks + chart descriptions |
| Airflow DAG | `edgar_ingestion` DAG: ingest → parse → upload → Snowflake load → dbt run → embed |

**Milestone:** Query `SELECT * FROM fct_financials WHERE ticker = 'AAPL'` returns 12 quarters of data. Cortex Search returns top-5 relevant text chunks. Image embedding search returns relevant charts for "revenue breakdown pie chart".

---

### Week 2 — Agent core + visual intelligence

**Goal:** Full LangGraph multi-agent graph working end-to-end locally, with text + chart retrieval

| Task | Details |
|---|---|
| LangGraph state schema | Define `FilingState`: query, query_type, company_list, retrieved_chunks, retrieved_charts, sql_results, anomaly_scores, final_answer |
| Supervisor agent | Classify query → `trend` / `comparison` / `anomaly`; detect visual intent; extract tickers and time range |
| SQL tool | Execute parameterised queries against dbt marts via Snowflake connector |
| Semantic tool | Call Cortex Search with query + filters (ticker, filing_type, date_range) |
| Visual tool | Query `voyage-multimodal-3` image embeddings; retrieve relevant charts/graphs with metadata |
| Anomaly scorer | Z-score over rolling 8-quarter window per metric; flag if \|z\| > 2.0 |
| Trend agent | Calls SQL tool + visual tool; structures time-series results + supporting charts |
| Comparison agent | Calls SQL + semantic + visual tools; diffs key metrics with chart evidence |
| Anomaly agent | Calls SQL tool + anomaly scorer; returns flagged metrics with context chunks |
| Synthesizer node | Merges text + chart results; calls Cortex LLM (multimodal) with structured prompt; returns cited answer with inline chart references |
| Local testing | pytest suite covering each agent and tool; test with AAPL, TSLA, NVDA filings |

**Milestone:** Query `"How has Apple's gross margin trended vs Microsoft over the last 3 years?"` returns a correct, cited multi-paragraph answer with relevant charts referenced. Query `"Show me revenue breakdown charts from Tesla's latest 10-K"` returns matching chart images.

---

### Week 3 — GKE deploy + autoscaling

**Goal:** Full system running on GKE Autopilot, autoscaling under load

| Task | Details |
|---|---|
| Dockerise | Multi-stage `Dockerfile` for FastAPI app; push to Artifact Registry |
| GKE Autopilot cluster | `gcloud container clusters create-auto fillingtinker --region us-central1` |
| FastAPI deployment | `fastapi-deployment.yaml` — 2 replicas, resource requests/limits, readiness probe |
| HPA | Scale FastAPI on CPU 60% threshold, min 2 / max 8 pods |
| KServe InferenceService | Serve quantized OSS embedding model (int8 ONNX); `kserve-inference.yaml` |
| KEDA ScaledObject | Queue-length based scaling for KServe pods; min 1 / max 6 |
| Airflow Helm deploy | `helm install airflow apache-airflow/airflow -f airflow-values.yaml`; mount DAG from GCS |
| NGINX ingress | TLS via cert-manager; route `/query` → FastAPI, `/health` → liveness |
| Load test | Locust from e2-micro VM; 50 concurrent users; verify KEDA pod scale-up |

**Milestone:** System handles 50 concurrent queries on GKE, KEDA scales pods from 1→4, p99 latency < 8s.

---

### Week 4 — Observability + polish

**Goal:** Production-grade monitoring, clean demo, public GitHub

| Task | Details |
|---|---|
| Cloud Monitoring | Custom metrics: query latency, agent hop count, tool call count, error rate |
| Grafana dashboard | Panels: p50/p99 latency, pod count over time, query type distribution, error rate |
| OpenTelemetry | Instrument FastAPI + LangGraph nodes with OTel spans; export to Cloud Trace |
| Canary rollout | KServe traffic split: 90% stable / 10% canary for new model version |
| Streamlit frontend | Company picker, date range selector, query type toggle, response with source citations + inline chart display |
| README | Architecture diagram, GIF demo, local setup guide, GKE deploy guide |
| Demo recording | Screen record: 3 query types live — trend, comparison, anomaly |
| LinkedIn post | Project writeup with architecture diagram and demo link |

**Milestone:** Public GitHub repo with full README, working Streamlit demo, Grafana screenshot.

---

## Sample Queries

| Type | Example |
|---|---|
| Trend | "How has Tesla's operating margin changed over the last 8 quarters?" |
| Comparison | "Compare Apple and Microsoft's R&D spend as % of revenue for 2023 vs 2024" |
| Anomaly | "Flag any unusual changes in Nvidia's risk factors between their last two 10-K filings" |
| Trend | "Show me Amazon's free cash flow trend since 2021" |
| Comparison | "Which company had better revenue growth in 2024 — Google or Meta?" |
| Visual | "Show me revenue breakdown charts from Apple's latest 10-K filing" |
| Visual | "Find charts showing Tesla's production capacity over time" |
| Cross-modal | "What do the graphs in Microsoft's latest annual report say about cloud revenue growth?" |
| Chart analysis | "Extract the data from Nvidia's GPU market share pie chart in their 2024 10-K" |

---

## GCP Free Tier Budget

| Resource | Usage | Cost |
|---|---|---|
| GKE Autopilot | 1 zonal cluster | Free |
| Compute e2-micro | Load test VM | Free (1/month) |
| Artifact Registry | ~200MB images | Free (0.5GB limit) |
| GCS | Raw filings + model weights | Free (5GB limit) |
| Cloud Monitoring | Metrics ingestion | Free (50GB limit) |
| **Total** | | **~$0/month** |

> Spin down GKE node pools when not actively developing to avoid pod resource charges.

---

## Stretch Goals

- Add a **report generation** agent that produces a 1-page PDF analyst summary with embedded charts
- Implement **filing diff** view — highlight exact sentence-level changes between two 10-K filings
- Add **earnings call transcript** ingestion alongside EDGAR filings
- Deploy Streamlit on **Snowflake Container Services** (as done in Meal Mind)
- Add **TruLens RAG evaluation** framework for retrieval quality monitoring
- Build **chart-to-table** extraction pipeline — convert all filing charts into structured tables via `AI_EXTRACT`
- Implement **cross-filing visual comparison** — find similar charts across companies/years using `voyage-multimodal-3` similarity
- Add **Cortex Analyst** semantic view integration for natural language SQL over financial marts
