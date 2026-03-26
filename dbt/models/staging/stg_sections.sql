-- stg_sections: cleaned filing sections
SELECT
    SECTION_ID,
    FILING_ID,
    LOWER(TRIM(SECTION_KEY))    AS SECTION_KEY,
    TRIM(SECTION_TITLE)         AS SECTION_TITLE,
    SECTION_TEXT,
    WORD_COUNT,
    START_OFFSET,
    END_OFFSET,
    LOADED_AT
FROM {{ source('raw', 'raw_filing_sections') }}
WHERE SECTION_TEXT IS NOT NULL
  AND LENGTH(SECTION_TEXT) > 50
