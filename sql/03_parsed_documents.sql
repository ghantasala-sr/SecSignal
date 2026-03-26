-- =============================================================================
-- SecSignal: Parsed documents, filing images, and chart extracts
-- Multimodal processing tables — fed by AI_PARSE_DOCUMENT + AI_EXTRACT
-- Run as SECSIGNAL_ADMIN after 02_raw_tables.sql
-- =============================================================================

USE DATABASE SECSIGNAL;
USE SCHEMA RAW;

-- ---------- Parsed document sections (from AI_PARSE_DOCUMENT LAYOUT mode) ----------
CREATE TABLE IF NOT EXISTS RAW.PARSED_SECTIONS (
    PARSED_SECTION_ID  VARCHAR(100)   NOT NULL,
    FILING_ID          VARCHAR(50)    NOT NULL,
    SECTION_INDEX      NUMBER         NOT NULL,   -- order within document
    CONTENT_TYPE       VARCHAR(20)    NOT NULL,   -- 'text', 'table', 'heading'
    CONTENT_TEXT       VARCHAR(16777216),
    PAGE_NUMBER        NUMBER,
    BOUNDING_BOX       VARIANT,                    -- spatial location on page
    LOADED_AT          TIMESTAMP_NTZ  DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT PK_PARSED_SECTIONS PRIMARY KEY (PARSED_SECTION_ID)
);

-- ---------- Filing images (charts, graphs, infographics extracted from PDFs) ----------
CREATE TABLE IF NOT EXISTS RAW.FILING_IMAGES (
    IMAGE_ID           VARCHAR(100)   NOT NULL,
    FILING_ID          VARCHAR(50)    NOT NULL,
    IMAGE_INDEX        NUMBER         NOT NULL,   -- order within document
    IMAGE_DATA_B64     VARCHAR(16777216),          -- base64-encoded image
    IMAGE_FORMAT       VARCHAR(10),                -- png, jpeg
    PAGE_NUMBER        NUMBER,
    BOUNDING_BOX       VARIANT,
    IMAGE_STAGE_PATH   VARCHAR(2000),              -- @FILING_IMAGES_STAGE/path
    DESCRIPTION        VARCHAR(10000),             -- AI_COMPLETE generated description
    LOADED_AT          TIMESTAMP_NTZ  DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT PK_FILING_IMAGES PRIMARY KEY (IMAGE_ID)
);

-- ---------- Chart extracts (structured data from AI_EXTRACT) ----------
CREATE TABLE IF NOT EXISTS RAW.CHART_EXTRACTS (
    EXTRACT_ID         VARCHAR(100)   NOT NULL,
    IMAGE_ID           VARCHAR(100)   NOT NULL,
    FILING_ID          VARCHAR(50)    NOT NULL,
    CHART_TYPE         VARCHAR(50),               -- bar, pie, line, area, table
    CHART_TITLE        VARCHAR(1000),
    EXTRACTED_DATA     VARIANT,                    -- structured JSON from AI_EXTRACT
    DATA_POINTS        NUMBER,                     -- count of extracted values
    CONFIDENCE_SCORE   FLOAT,
    LOADED_AT          TIMESTAMP_NTZ  DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT PK_CHART_EXTRACTS PRIMARY KEY (EXTRACT_ID),
    CONSTRAINT FK_CHART_IMAGE FOREIGN KEY (IMAGE_ID)
        REFERENCES RAW.FILING_IMAGES (IMAGE_ID)
);
