"""Visual search tool — cross-modal chart retrieval via voyage-multimodal-3.

Embeds text queries in the same vector space as chart images using
SNOWFLAKE.CORTEX.EMBED_TEXT_1024('voyage-multimodal-3', query), then
finds matching images via VECTOR_COSINE_SIMILARITY.
"""

from __future__ import annotations

from typing import Any

import structlog

from secsignal.agents.connection import get_snowflake_connection

logger = structlog.get_logger(__name__)

IMAGE_EMBED_MODEL = "voyage-multimodal-3"


def search_charts(
    query: str,
    ticker: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Find chart images matching a text query via cross-modal similarity.

    Uses voyage-multimodal-3 to embed the text query in the same vector
    space as chart image embeddings, then ranks by cosine similarity.

    Args:
        query: Text query (e.g. 'revenue breakdown pie chart').
        ticker: Filter by ticker. None for all.
        limit: Max results.

    Returns:
        List of dicts with image_id, description, ticker, chart_type,
        image_data_b64, similarity score.
    """
    conn = get_snowflake_connection()
    cursor = conn.cursor()
    try:
        conditions = []
        params: list[Any] = [IMAGE_EMBED_MODEL, query]

        if ticker:
            conditions.append("ie.TICKER = %s")
            params.append(ticker.upper())

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        sql = f"""
            SELECT
                ie.IMAGE_ID,
                ie.DESCRIPTION,
                ie.TICKER,
                ie.FILING_TYPE,
                ie.FILING_DATE,
                ie.CHART_TYPE,
                fi.IMAGE_DATA_B64,
                fi.PAGE_NUMBER,
                cd.CHART_TITLE,
                cd.CONFIDENCE_SCORE,
                VECTOR_COSINE_SIMILARITY(
                    ie.EMBEDDING,
                    SNOWFLAKE.CORTEX.EMBED_TEXT_1024(%s, %s)::VECTOR(FLOAT, 1024)
                ) AS similarity
            FROM SECSIGNAL.RAW.IMAGE_EMBEDDINGS ie
            JOIN SECSIGNAL.RAW.FILING_IMAGES fi ON ie.IMAGE_ID = fi.IMAGE_ID
            LEFT JOIN SECSIGNAL.MARTS.FCT_CHART_DATA cd ON ie.IMAGE_ID = cd.IMAGE_ID
            {where}
            ORDER BY similarity DESC
            LIMIT %s
        """
        cursor.execute(sql, params)
        columns = [desc[0] for desc in cursor.description]
        raw_rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        # Filter out low-quality results (logos, decorative images)
        rows = []
        for r in raw_rows:
            desc = r.get("DESCRIPTION") or ""
            chart_type = r.get("CHART_TYPE")
            page = r.get("PAGE_NUMBER", 0)
            confidence = r.get("CONFIDENCE_SCORE") or 0

            # Skip if: page 0, no real chart type, no description, low confidence
            is_logo = (
                page == 0
                and (not chart_type or chart_type in ("None", "unknown"))
                and ("Filing image from page" in desc or not desc.strip())
                and confidence == 0
            )
            if not is_logo:
                rows.append(r)

        if not rows and raw_rows:
            # If all filtered out, return top results with a warning flag
            logger.warning(
                "search_charts_all_filtered",
                query=query[:50],
                total=len(raw_rows),
                msg="All images appear to be logos/decorative. Returning top results anyway.",
            )
            for r in raw_rows:
                r["_warning"] = "This image may be a logo or decorative element, not a financial chart."
            rows = raw_rows

        logger.debug("search_charts", query=query[:50], ticker=ticker, results=len(rows))
        return rows

    except Exception:
        logger.exception("search_charts_failed", query=query[:50])
        return []
    finally:
        cursor.close()
