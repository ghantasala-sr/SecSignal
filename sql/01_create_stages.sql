-- =============================================================================
-- SecSignal: Stages — internal (images, parsed docs) + external (GCS)
-- Run as SECSIGNAL_ADMIN after 00_setup_database.sql
-- =============================================================================

USE DATABASE SECSIGNAL;
USE SCHEMA RAW;

-- ---------- External Stage: GCS raw filings ----------
-- Requires a storage integration. Create that first if it doesn't exist.
-- Replace <your_gcs_bucket> with the actual bucket name.

-- CREATE STORAGE INTEGRATION IF NOT EXISTS SECSIGNAL_GCS_INT
--     TYPE = EXTERNAL_STAGE
--     STORAGE_PROVIDER = 'GCS'
--     STORAGE_ALLOWED_LOCATIONS = ('gcs://secsignal-raw/')
--     ENABLED = TRUE;

-- GRANT USAGE ON INTEGRATION SECSIGNAL_GCS_INT TO ROLE SECSIGNAL_ADMIN;

CREATE STAGE IF NOT EXISTS RAW.GCS_FILINGS_STAGE
    -- URL = 'gcs://secsignal-raw/'               -- uncomment after integration
    -- STORAGE_INTEGRATION = SECSIGNAL_GCS_INT     -- uncomment after integration
    FILE_FORMAT = (TYPE = 'JSON')
    COMMENT = 'External stage pointing to GCS bucket with raw EDGAR filings';

-- ---------- Internal Stage: PDF documents for AI_PARSE_DOCUMENT ----------
CREATE STAGE IF NOT EXISTS RAW.FILING_DOCUMENTS_STAGE
    ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
    COMMENT = 'Internal stage for PDF filings to be parsed by AI_PARSE_DOCUMENT';

-- ---------- Internal Stage: Extracted chart/graph images ----------
CREATE STAGE IF NOT EXISTS RAW.FILING_IMAGES_STAGE
    ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
    COMMENT = 'Internal stage for extracted chart/graph images from filings';

-- ---------- File Formats ----------
CREATE FILE FORMAT IF NOT EXISTS RAW.JSON_FORMAT
    TYPE = 'JSON'
    STRIP_OUTER_ARRAY = TRUE
    COMMENT = 'JSON file format for EDGAR API responses';

CREATE FILE FORMAT IF NOT EXISTS RAW.CSV_FORMAT
    TYPE = 'CSV'
    FIELD_OPTIONALLY_ENCLOSED_BY = '"'
    SKIP_HEADER = 1
    COMMENT = 'CSV file format for tabular filing data';

CREATE FILE FORMAT IF NOT EXISTS RAW.PARQUET_FORMAT
    TYPE = 'PARQUET'
    COMMENT = 'Parquet format for structured filing extracts';
