-- =============================================================================
-- SecSignal: Stages — internal (images, parsed docs) + external (GCS)
-- Run as SECSIGNAL_ADMIN after 00_setup_database.sql
-- =============================================================================

USE DATABASE SECSIGNAL;
USE SCHEMA RAW;

-- ---------- Storage Integration: Snowflake → GCS ----------
CREATE STORAGE INTEGRATION IF NOT EXISTS SECSIGNAL_GCS_INT
    TYPE = EXTERNAL_STAGE
    STORAGE_PROVIDER = 'GCS'
    STORAGE_ALLOWED_LOCATIONS = ('gcs://secsignal-raw/')
    ENABLED = TRUE;

-- After creating, run: DESCRIBE INTEGRATION SECSIGNAL_GCS_INT;
-- Grant the STORAGE_GCP_SERVICE_ACCOUNT read access on the GCS bucket.

CREATE OR REPLACE STAGE RAW.GCS_FILINGS_STAGE
    URL = 'gcs://secsignal-raw/'
    STORAGE_INTEGRATION = SECSIGNAL_GCS_INT
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
