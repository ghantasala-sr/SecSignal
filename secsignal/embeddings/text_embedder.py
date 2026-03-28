"""Text embedding using Snowflake Cortex EMBED_TEXT_1024 with snowflake-arctic-embed-l-v2.0-8k.

Produces 1024-dimensional vectors for filing text chunks. Supports batching
via SQL for efficient embedding of large document sets.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

MODEL = "snowflake-arctic-embed-l-v2.0-8k"
EMBEDDING_DIM = 1024


class TextEmbedder:
    """Embed text chunks using Cortex EMBED_TEXT_1024 with Arctic embed model.

    Vectors are 1024-dimensional, supporting up to 8K tokens per input.
    """

    def __init__(self, snowflake_connection: Any, model: str = MODEL) -> None:
        self._conn = snowflake_connection
        self._model = model

    def embed_single(self, text: str) -> list[float] | None:
        """Embed a single text string.

        Args:
            text: Input text (up to 8K tokens).

        Returns:
            List of floats (1024 dims), or None on error.
        """
        cursor = self._conn.cursor()
        try:
            cursor.execute(
                "SELECT SNOWFLAKE.CORTEX.EMBED_TEXT_1024(%s, %s)::VECTOR(FLOAT, 1024) AS emb",
                (self._model, text),
            )
            row = cursor.fetchone()
            return row[0] if row else None
        except Exception:
            logger.exception("text_embed_failed", text_len=len(text))
            return None
        finally:
            cursor.close()

    def embed_and_store_chunks(
        self,
        chunks: list[dict[str, Any]],
    ) -> int:
        """Embed text chunks and insert into TEXT_EMBEDDINGS table.

        Each chunk dict must contain:
            - text: str
            - filing_id: str
            - section_key: str
            - chunk_index: int
            - ticker: str
            - filing_type: str
            - filing_date: str

        Returns:
            Number of rows inserted.
        """
        if not chunks:
            return 0

        cursor = self._conn.cursor()
        inserted = 0
        try:
            for chunk in chunks:
                chunk_id = _generate_chunk_id(chunk["filing_id"], chunk["section_key"], chunk["chunk_index"])
                cursor.execute(
                    """
                    INSERT INTO SECSIGNAL.RAW.TEXT_EMBEDDINGS
                        (CHUNK_ID, FILING_ID, SECTION_KEY, CHUNK_INDEX, CHUNK_TEXT,
                         TICKER, FILING_TYPE, FILING_DATE, EMBEDDING)
                    SELECT
                        %s, %s, %s, %s, %s, %s, %s, %s,
                        SNOWFLAKE.CORTEX.EMBED_TEXT_1024(%s, %s)::VECTOR(FLOAT, 1024)
                    """,
                    (
                        chunk_id,
                        chunk["filing_id"],
                        chunk["section_key"],
                        chunk["chunk_index"],
                        chunk["text"],
                        chunk["ticker"],
                        chunk["filing_type"],
                        chunk["filing_date"],
                        self._model,
                        chunk["text"],
                    ),
                )
                inserted += 1
            return inserted
        finally:
            cursor.close()

    def bulk_embed_from_sections(self, filing_id: str) -> int:
        """Embed all sections for a filing directly via SQL (server-side).

        This runs the embedding entirely within Snowflake — no data transfer.

        Returns:
            Number of chunks embedded.
        """
        cursor = self._conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO SECSIGNAL.RAW.TEXT_EMBEDDINGS
                    (CHUNK_ID, FILING_ID, SECTION_KEY, CHUNK_INDEX, CHUNK_TEXT,
                     TICKER, FILING_TYPE, FILING_DATE, EMBEDDING)
                SELECT
                    CONCAT('chunk_', MD5(CONCAT(s.FILING_ID, s.SECTION_KEY, '0'))),
                    s.FILING_ID,
                    s.SECTION_KEY,
                    0,
                    s.SECTION_TEXT,
                    f.TICKER,
                    f.FILING_TYPE,
                    f.FILING_DATE,
                    SNOWFLAKE.CORTEX.EMBED_TEXT_1024(%s, s.SECTION_TEXT)::VECTOR(FLOAT, 1024)
                FROM SECSIGNAL.RAW.RAW_FILING_SECTIONS s
                JOIN SECSIGNAL.RAW.RAW_FILINGS f ON s.FILING_ID = f.FILING_ID
                WHERE s.FILING_ID = %s
                    AND s.SECTION_TEXT IS NOT NULL
                    AND LENGTH(s.SECTION_TEXT) > 50
                """,
                (self._model, filing_id),
            )
            return cursor.rowcount
        finally:
            cursor.close()


def _generate_chunk_id(filing_id: str, section_key: str, chunk_index: int) -> str:
    """Deterministic chunk ID for deduplication."""
    content = f"{filing_id}:{section_key}:{chunk_index}"
    return f"chunk_{hashlib.sha256(content.encode()).hexdigest()[:16]}"
