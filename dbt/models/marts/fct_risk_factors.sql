-- fct_risk_factors: risk factor text per company per filing
-- Key mart for anomaly detection and semantic search
SELECT
    ps.SECTION_ID               AS RISK_FACTOR_ID,
    ps.FILING_ID,
    ps.TICKER,
    ps.COMPANY_NAME,
    ps.FILING_TYPE,
    ps.FILING_DATE,
    ps.FISCAL_QUARTER,
    ps.SECTION_TITLE,
    ps.SECTION_TEXT              AS RISK_FACTOR_TEXT,
    ps.WORD_COUNT,
    -- Change detection: word count delta vs prior filing
    LAG(ps.WORD_COUNT) OVER (
        PARTITION BY ps.TICKER
        ORDER BY ps.FILING_DATE
    )                           AS PREV_WORD_COUNT,
    ps.WORD_COUNT - COALESCE(
        LAG(ps.WORD_COUNT) OVER (
            PARTITION BY ps.TICKER
            ORDER BY ps.FILING_DATE
        ), ps.WORD_COUNT
    )                           AS WORD_COUNT_DELTA
FROM {{ ref('int_parsed_sections') }} ps
WHERE ps.SECTION_KEY = 'item_1a'
