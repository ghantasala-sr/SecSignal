-- dim_filing_images: dimension table for all chart/graph images
-- Maps images to filings with descriptions and metadata
SELECT
    fi.IMAGE_ID,
    fi.FILING_ID,
    f.TICKER,
    f.FILING_TYPE,
    f.FILING_DATE,
    c.COMPANY_NAME,
    fi.IMAGE_INDEX,
    fi.IMAGE_FORMAT,
    fi.PAGE_NUMBER,
    fi.DESCRIPTION,
    fi.ESTIMATED_SIZE_BYTES,
    DATE_TRUNC('quarter', f.FILING_DATE) AS FISCAL_QUARTER
FROM {{ ref('stg_filing_images') }} fi
JOIN {{ ref('stg_filings') }} f ON fi.FILING_ID = f.FILING_ID
JOIN {{ ref('stg_companies') }} c ON f.CIK = c.CIK
