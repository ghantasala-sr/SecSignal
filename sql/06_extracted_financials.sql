-- Extracted financial metrics from MD&A sections via Cortex COMPLETE.
-- Populated by scripts/extract_financials.py

CREATE TABLE IF NOT EXISTS SECSIGNAL.RAW.EXTRACTED_FINANCIALS (
    EXTRACT_ID   VARCHAR(100)    PRIMARY KEY,
    FILING_ID    VARCHAR(50),
    TICKER       VARCHAR(10),
    FILING_TYPE  VARCHAR(10),
    FILING_DATE  DATE,
    METRIC_NAME  VARCHAR(200),
    METRIC_CATEGORY VARCHAR(100),   -- e.g. 'revenue', 'operating_income', 'margin'
    VALUE        FLOAT,
    PERIOD       VARCHAR(200),      -- e.g. 'Q1 2024', 'FY 2023'
    UNIT         VARCHAR(50),       -- e.g. 'USD_millions', 'percent'
    EXTRACTED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);
