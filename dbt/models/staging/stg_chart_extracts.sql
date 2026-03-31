-- stg_chart_extracts: cleaned chart extract metadata
SELECT
    EXTRACT_ID,
    IMAGE_ID,
    FILING_ID,
    TRIM(CHART_TYPE)              AS CHART_TYPE,
    TRIM(CHART_TITLE)             AS CHART_TITLE,
    EXTRACTED_DATA,
    DATA_POINTS,
    CONFIDENCE_SCORE,
    LOADED_AT
FROM {{ source('raw', 'chart_extracts') }}
WHERE EXTRACT_ID IS NOT NULL
  AND CONFIDENCE_SCORE >= 0
