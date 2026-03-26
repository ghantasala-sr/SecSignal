-- =============================================================================
-- SecSignal: Cortex Search service over combined text + chart descriptions
-- Run as SECSIGNAL_ADMIN after 04_embedding_tables.sql
-- =============================================================================

USE DATABASE SECSIGNAL;

-- ---------- Cortex Search Service ----------
-- Creates a search service over the SEARCH_CORPUS table
-- This enables semantic search across both filing text chunks and chart descriptions

CREATE OR REPLACE CORTEX SEARCH SERVICE SECSIGNAL.RAW.FILING_SEARCH_SERVICE
    ON CONTENT
    ATTRIBUTES TICKER, FILING_TYPE, FILING_DATE, CONTENT_TYPE, SECTION_KEY
    WAREHOUSE = SECSIGNAL_CORTEX_WH
    TARGET_LAG = '1 hour'
    AS (
        SELECT
            CORPUS_ID,
            FILING_ID,
            TICKER,
            FILING_TYPE,
            FILING_DATE,
            CONTENT_TYPE,
            CONTENT,
            SOURCE_ID,
            SECTION_KEY
        FROM SECSIGNAL.RAW.SEARCH_CORPUS
    );

-- NOTE: Cortex Search automatically handles embedding and indexing.
-- Queries can filter by TICKER, FILING_TYPE, CONTENT_TYPE etc.
--
-- Example query (from Python):
--   search_service.search(
--       query="revenue breakdown by segment",
--       columns=["CONTENT", "TICKER", "FILING_TYPE", "CONTENT_TYPE"],
--       filter={"@eq": {"TICKER": "AAPL"}},
--       limit=10
--   )
