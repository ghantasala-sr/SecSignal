-- stg_companies: cleaned company master from RAW
SELECT
    CIK,
    UPPER(TRIM(TICKER))         AS TICKER,
    TRIM(COMPANY_NAME)          AS COMPANY_NAME,
    SIC_CODE,
    STATE,
    FISCAL_YEAR_END,
    LOADED_AT
FROM {{ source('raw', 'raw_companies') }}
WHERE CIK IS NOT NULL
  AND TICKER IS NOT NULL
