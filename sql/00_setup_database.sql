-- =============================================================================
-- SecSignal: Database and Schemas Setup
-- Run as TRAINING_ROLE (your existing role — no custom roles needed)
-- =============================================================================

-- ---------- Database ----------
CREATE DATABASE IF NOT EXISTS SECSIGNAL
    COMMENT = 'SEC EDGAR financial intelligence — agentic RAG system';

-- ---------- Schemas ----------
CREATE SCHEMA IF NOT EXISTS SECSIGNAL.RAW
    COMMENT = 'Raw ingested data from EDGAR and GCS';

CREATE SCHEMA IF NOT EXISTS SECSIGNAL.STAGING
    COMMENT = 'Cleaned and normalized staging models (dbt)';

CREATE SCHEMA IF NOT EXISTS SECSIGNAL.INTERMEDIATE
    COMMENT = 'Intermediate transforms — parsed sections, chart extracts';

CREATE SCHEMA IF NOT EXISTS SECSIGNAL.MARTS
    COMMENT = 'Business-ready fact and dimension tables';

CREATE SCHEMA IF NOT EXISTS SECSIGNAL.EVALUATION
    COMMENT = 'RAG evaluation metrics and test results';

CREATE SCHEMA IF NOT EXISTS SECSIGNAL.MONITORING
    COMMENT = 'Pipeline health, freshness checks, observability';
