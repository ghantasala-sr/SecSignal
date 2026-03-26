-- stg_filings: cleaned filing metadata
SELECT
    FILING_ID,
    CIK,
    UPPER(TRIM(TICKER))         AS TICKER,
    UPPER(TRIM(FILING_TYPE))    AS FILING_TYPE,
    FILING_DATE,
    PRIMARY_DOCUMENT,
    DOCUMENT_URL,
    GCS_URI,
    FILE_SIZE_BYTES,
    LOADED_AT
FROM {{ source('raw', 'raw_filings') }}
WHERE FILING_ID IS NOT NULL
  AND FILING_TYPE IN ('10-K', '10-Q', '8-K')
