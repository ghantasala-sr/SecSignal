-- fct_financials: core financial metrics per company per quarter
-- Placeholder — will be populated from XBRL-extracted financial data
-- TODO: Wire up XBRL taxonomy parsing for revenue, EPS, debt ratios
SELECT
    ps.FILING_ID,
    ps.TICKER,
    ps.COMPANY_NAME,
    ps.FILING_TYPE,
    ps.FILING_DATE,
    ps.FISCAL_QUARTER,
    ps.SECTION_KEY,
    ps.SECTION_TITLE,
    ps.WORD_COUNT
FROM {{ ref('int_parsed_sections') }} ps
WHERE ps.SECTION_KEY = 'item_8'
