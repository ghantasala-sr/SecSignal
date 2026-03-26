-- =============================================================================
-- SecSignal: Embedding tables — text (Arctic) + image (voyage-multimodal-3)
-- Run as SECSIGNAL_ADMIN after 03_parsed_documents.sql
-- =============================================================================

USE DATABASE SECSIGNAL;
USE SCHEMA RAW;

-- ---------- Text chunk embeddings (snowflake-arctic-embed-l-v2.0-8k, 1024 dims) ----------
CREATE TABLE IF NOT EXISTS RAW.TEXT_EMBEDDINGS (
    CHUNK_ID           VARCHAR(100)   NOT NULL,
    FILING_ID          VARCHAR(50)    NOT NULL,
    SECTION_KEY        VARCHAR(20),
    CHUNK_INDEX        NUMBER         NOT NULL,
    CHUNK_TEXT         VARCHAR(16777216),
    TICKER             VARCHAR(10),
    FILING_TYPE        VARCHAR(10),
    FILING_DATE        DATE,
    EMBEDDING          VECTOR(FLOAT, 1024),         -- Arctic embed output
    CREATED_AT         TIMESTAMP_NTZ  DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT PK_TEXT_EMBEDDINGS PRIMARY KEY (CHUNK_ID)
);

-- ---------- Image embeddings (voyage-multimodal-3, cross-modal) ----------
-- voyage-multimodal-3 produces 1024-dim vectors for both text and images
CREATE TABLE IF NOT EXISTS RAW.IMAGE_EMBEDDINGS (
    EMBEDDING_ID       VARCHAR(100)   NOT NULL,
    IMAGE_ID           VARCHAR(100)   NOT NULL,
    FILING_ID          VARCHAR(50)    NOT NULL,
    TICKER             VARCHAR(10),
    FILING_TYPE        VARCHAR(10),
    FILING_DATE        DATE,
    CHART_TYPE         VARCHAR(50),
    DESCRIPTION        VARCHAR(10000),
    EMBEDDING          VECTOR(FLOAT, 1024),         -- voyage-multimodal-3 output
    CREATED_AT         TIMESTAMP_NTZ  DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT PK_IMAGE_EMBEDDINGS PRIMARY KEY (EMBEDDING_ID),
    CONSTRAINT FK_IMAGE_EMBED_IMAGE FOREIGN KEY (IMAGE_ID)
        REFERENCES RAW.FILING_IMAGES (IMAGE_ID)
);

-- ---------- Combined search corpus (for Cortex Search service) ----------
CREATE TABLE IF NOT EXISTS RAW.SEARCH_CORPUS (
    CORPUS_ID          VARCHAR(100)   NOT NULL,
    FILING_ID          VARCHAR(50)    NOT NULL,
    TICKER             VARCHAR(10),
    FILING_TYPE        VARCHAR(10),
    FILING_DATE        DATE,
    CONTENT_TYPE       VARCHAR(20)    NOT NULL,   -- 'text_chunk' or 'chart_description'
    CONTENT            VARCHAR(16777216),
    SOURCE_ID          VARCHAR(100),               -- chunk_id or image_id
    SECTION_KEY        VARCHAR(20),
    CREATED_AT         TIMESTAMP_NTZ  DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT PK_SEARCH_CORPUS PRIMARY KEY (CORPUS_ID)
);
