-- =============================================================================
-- SecSignal: RAW schema tables for ingested EDGAR filings
-- Run as SECSIGNAL_ADMIN after 01_create_stages.sql
-- =============================================================================

USE DATABASE SECSIGNAL;
USE SCHEMA RAW;

-- ---------- Companies (CIK → ticker mapping) ----------
CREATE TABLE IF NOT EXISTS RAW.RAW_COMPANIES (
    CIK              VARCHAR(10)    NOT NULL,
    TICKER           VARCHAR(10)    NOT NULL,
    COMPANY_NAME     VARCHAR(500)   NOT NULL,
    SIC_CODE         VARCHAR(10),
    STATE            VARCHAR(50),
    FISCAL_YEAR_END  VARCHAR(4),
    LOADED_AT        TIMESTAMP_NTZ  DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT PK_RAW_COMPANIES PRIMARY KEY (CIK)
);

-- ---------- Filings metadata ----------
CREATE TABLE IF NOT EXISTS RAW.RAW_FILINGS (
    FILING_ID          VARCHAR(50)    NOT NULL,  -- accession number
    CIK                VARCHAR(10)    NOT NULL,
    TICKER             VARCHAR(10),
    FILING_TYPE        VARCHAR(10)    NOT NULL,   -- 10-K, 10-Q, 8-K
    FILING_DATE        DATE           NOT NULL,
    PRIMARY_DOCUMENT   VARCHAR(500),
    DOCUMENT_URL       VARCHAR(2000),
    GCS_URI            VARCHAR(2000),
    FILE_SIZE_BYTES    NUMBER,
    LOADED_AT          TIMESTAMP_NTZ  DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT PK_RAW_FILINGS PRIMARY KEY (FILING_ID)
);

-- ---------- Filing sections (parsed text by Item) ----------
CREATE TABLE IF NOT EXISTS RAW.RAW_FILING_SECTIONS (
    SECTION_ID         VARCHAR(100)   NOT NULL,  -- filing_id + section_key
    FILING_ID          VARCHAR(50)    NOT NULL,
    SECTION_KEY        VARCHAR(20)    NOT NULL,   -- item_1, item_1a, item_7, etc.
    SECTION_TITLE      VARCHAR(500),
    SECTION_TEXT        VARCHAR(16777216),         -- up to 16MB for large sections
    WORD_COUNT         NUMBER,
    START_OFFSET       NUMBER,
    END_OFFSET         NUMBER,
    LOADED_AT          TIMESTAMP_NTZ  DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT PK_RAW_FILING_SECTIONS PRIMARY KEY (SECTION_ID),
    CONSTRAINT FK_SECTION_FILING FOREIGN KEY (FILING_ID)
        REFERENCES RAW.RAW_FILINGS (FILING_ID)
);
