-- stg_filing_images: cleaned chart/graph image metadata
SELECT
    IMAGE_ID,
    FILING_ID,
    IMAGE_INDEX,
    IMAGE_FORMAT,
    PAGE_NUMBER,
    BOUNDING_BOX,
    DESCRIPTION,
    LENGTH(IMAGE_DATA_B64) * 3 / 4 AS ESTIMATED_SIZE_BYTES,
    LOADED_AT
FROM {{ source('raw', 'filing_images') }}
WHERE IMAGE_ID IS NOT NULL
  AND IMAGE_DATA_B64 IS NOT NULL
