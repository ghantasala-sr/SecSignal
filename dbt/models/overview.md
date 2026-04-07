{% docs __overview__ %}

# SecSignal dbt Documentation

**SecSignal** is a production-grade Agentic RAG system for SEC financial intelligence, powered by Snowflake Cortex AI, LangGraph, and Apache Airflow.

## Data Pipeline

Raw SEC EDGAR filings are ingested weekly by the `secsignal_ingest_filings` Airflow DAG, archived to Google Cloud Storage, parsed into sections, and loaded into Snowflake. dbt then transforms the raw data through three layers into analytics-ready tables.

## Model Layers

### Staging (`stg_*`)
Views that clean and standardize raw data. Apply `UPPER(TRIM())` to tickers, `LOWER(TRIM())` to section keys, filter to valid form types (10-K, 10-Q, 8-K), and enforce minimum text quality (LENGTH > 50 characters). No joins at this layer.

| Model | Description |
|-------|-------------|
| `stg_companies` | Company master — CIK to ticker mapping |
| `stg_filings` | Filing metadata filtered to 10-K, 10-Q, 8-K |
| `stg_sections` | Filing sections with text quality gate |
| `stg_filing_images` | Chart/graph image metadata with estimated sizes |
| `stg_chart_extracts` | AI_EXTRACT results with confidence filtering |

### Intermediate (`int_*`)
Tables that join staging models to add company and filing context. Compute `FISCAL_QUARTER` via `DATE_TRUNC('quarter', FILING_DATE)`.

| Model | Description |
|-------|-------------|
| `int_parsed_sections` | Sections enriched with ticker, company name, filing context |
| `int_chart_extracts` | Chart extractions enriched with image and filing context |

### Marts (`fct_*`, `dim_*`)
Business-facing tables consumed by the LangGraph agents, FastAPI endpoints, and the Cortex Search embedding pipeline.

| Model | Description |
|-------|-------------|
| `fct_risk_factors` | SEC Item 1A text with LAG-based word count change detection |
| `fct_financials` | SEC Item 8 financial statements (placeholder for XBRL) |
| `fct_chart_data` | Structured numeric data extracted from filing charts |
| `dim_filing_images` | Image dimension table for the /api/charts endpoint |

## Sources

All models trace back to 5 raw tables in the `SECSIGNAL.RAW` schema, populated by the ingestion pipeline:

- **raw_companies** — CIK/ticker mapping from EDGAR
- **raw_filings** — Filing metadata from EDGAR Submissions API
- **raw_filing_sections** — Section text parsed by BeautifulSoup
- **filing_images** — Chart images extracted via AI_PARSE_DOCUMENT
- **chart_extracts** — Structured data from AI_EXTRACT

## Downstream Consumers

- **Cortex Search Service** (`FILING_SEARCH_SERVICE`) — fed by `int_parsed_sections` via the `SEARCH_CORPUS` table
- **Text Embeddings** — Arctic embed vectors generated from `int_parsed_sections`
- **Image Embeddings** — Voyage multimodal-3 vectors from `filing_images`
- **LangGraph Agents** — `trend_agent`, `valuation_agent`, `sentiment_agent`, and `anomaly_agent` query mart tables directly

{% enddocs %}
