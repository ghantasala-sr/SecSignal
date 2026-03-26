-- fct_chart_data: structured data extracted from filing charts
-- Enables SQL-queryable chart data alongside narrative content
SELECT
    ce.EXTRACT_ID,
    ce.IMAGE_ID,
    ce.FILING_ID,
    ce.TICKER,
    ce.COMPANY_NAME,
    ce.FILING_TYPE,
    ce.FILING_DATE,
    ce.FISCAL_QUARTER,
    ce.CHART_TYPE,
    ce.CHART_TITLE,
    ce.EXTRACTED_DATA,
    ce.DATA_POINTS,
    ce.CONFIDENCE_SCORE,
    ce.IMAGE_DESCRIPTION,
    ce.PAGE_NUMBER
FROM {{ ref('int_chart_extracts') }} ce
