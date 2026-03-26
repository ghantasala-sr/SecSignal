-- int_parsed_sections: join filing sections with filing metadata
-- Enriches sections with company ticker and filing context
SELECT
    s.SECTION_ID,
    s.FILING_ID,
    f.TICKER,
    f.FILING_TYPE,
    f.FILING_DATE,
    c.COMPANY_NAME,
    s.SECTION_KEY,
    s.SECTION_TITLE,
    s.SECTION_TEXT,
    s.WORD_COUNT,
    DATE_TRUNC('quarter', f.FILING_DATE) AS FISCAL_QUARTER
FROM {{ ref('stg_sections') }} s
JOIN {{ ref('stg_filings') }} f ON s.FILING_ID = f.FILING_ID
JOIN {{ ref('stg_companies') }} c ON f.CIK = c.CIK
