-- int_chart_extracts: enrich chart extracts with filing + image context
SELECT
    ce.EXTRACT_ID,
    ce.IMAGE_ID,
    ce.FILING_ID,
    f.TICKER,
    f.FILING_TYPE,
    f.FILING_DATE,
    c.COMPANY_NAME,
    ce.CHART_TYPE,
    ce.CHART_TITLE,
    ce.EXTRACTED_DATA,
    ce.DATA_POINTS,
    ce.CONFIDENCE_SCORE,
    fi.IMAGE_FORMAT,
    fi.PAGE_NUMBER,
    fi.DESCRIPTION AS IMAGE_DESCRIPTION,
    DATE_TRUNC('quarter', f.FILING_DATE) AS FISCAL_QUARTER
FROM {{ ref('stg_chart_extracts') }} ce
JOIN {{ ref('stg_filing_images') }} fi ON ce.IMAGE_ID = fi.IMAGE_ID
JOIN {{ ref('stg_filings') }} f ON ce.FILING_ID = f.FILING_ID
JOIN {{ ref('stg_companies') }} c ON f.CIK = c.CIK
