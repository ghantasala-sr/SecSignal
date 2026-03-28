"""Dual embedding orchestrator — coordinates text and image embedding pipelines.

Manages the end-to-end flow:
1. Text chunks → Arctic embed (1024d) → TEXT_EMBEDDINGS
2. Chart images → voyage-multimodal-3 (1024d) → IMAGE_EMBEDDINGS
3. Both → SEARCH_CORPUS for Cortex Search service
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from secsignal.embeddings.image_embedder import ImageEmbedder
from secsignal.embeddings.text_embedder import TextEmbedder
from secsignal.processing.image_extractor import ExtractedImage

logger = structlog.get_logger(__name__)


class CortexEmbedder:
    """Orchestrates dual embedding: text (Arctic) + image (voyage-multimodal-3).

    Both produce 1024-dimensional vectors but in different semantic spaces:
    - Arctic: text-to-text similarity
    - Voyage multimodal: cross-modal text↔image similarity

    Also populates the SEARCH_CORPUS table used by Cortex Search.
    """

    def __init__(self, snowflake_connection: Any) -> None:
        self._conn = snowflake_connection
        self._text_embedder = TextEmbedder(snowflake_connection)
        self._image_embedder = ImageEmbedder(snowflake_connection)

    def embed_filing_text(self, chunks: list[dict[str, Any]]) -> int:
        """Embed text chunks and populate TEXT_EMBEDDINGS + SEARCH_CORPUS.

        Args:
            chunks: List of chunk dicts (see TextEmbedder.embed_and_store_chunks).

        Returns:
            Number of chunks embedded.
        """
        count = self._text_embedder.embed_and_store_chunks(chunks)

        # Also insert into search corpus for Cortex Search
        self._insert_text_corpus(chunks)

        logger.info("embedded_text", chunks=count)
        return count

    def embed_filing_images(
        self,
        images: list[ExtractedImage],
        descriptions: dict[str, str],
        filing_metadata: dict[str, Any],
    ) -> int:
        """Embed chart images and populate IMAGE_EMBEDDINGS + SEARCH_CORPUS.

        Args:
            images: List of extracted chart images.
            descriptions: Dict of image_id → text description.
            filing_metadata: Dict with ticker, filing_type, filing_date.

        Returns:
            Number of images embedded.
        """
        count = self._image_embedder.embed_and_store_images(images, descriptions, filing_metadata)

        # Insert chart descriptions into search corpus
        self._insert_image_corpus(images, descriptions, filing_metadata)

        logger.info("embedded_images", images=count)
        return count

    def search_similar_text(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Find similar text chunks using Arctic embeddings.

        Args:
            query: Search query text.
            limit: Number of results to return.

        Returns:
            List of dicts with chunk_id, chunk_text, ticker, similarity_score.
        """
        cursor = self._conn.cursor()
        try:
            cursor.execute(
                """
                SELECT
                    CHUNK_ID,
                    CHUNK_TEXT,
                    TICKER,
                    FILING_TYPE,
                    FILING_DATE,
                    VECTOR_COSINE_SIMILARITY(
                        EMBEDDING,
                        SNOWFLAKE.CORTEX.EMBED_TEXT_1024('snowflake-arctic-embed-l-v2.0-8k', %s)::VECTOR(FLOAT, 1024)
                    ) AS similarity
                FROM SECSIGNAL.RAW.TEXT_EMBEDDINGS
                ORDER BY similarity DESC
                LIMIT %s
                """,
                (query, limit),
            )
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            cursor.close()

    def search_similar_images(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Find similar chart images using cross-modal voyage-multimodal-3 embeddings.

        Text query is embedded in the same cross-modal space as chart images.

        Args:
            query: Text query (e.g. "revenue breakdown pie chart").
            limit: Number of results.

        Returns:
            List of dicts with image_id, description, ticker, similarity_score.
        """
        cursor = self._conn.cursor()
        try:
            cursor.execute(
                """
                SELECT
                    ie.IMAGE_ID,
                    ie.DESCRIPTION,
                    ie.TICKER,
                    ie.FILING_TYPE,
                    ie.FILING_DATE,
                    ie.CHART_TYPE,
                    fi.IMAGE_DATA_B64,
                    VECTOR_COSINE_SIMILARITY(
                        ie.EMBEDDING,
                        SNOWFLAKE.CORTEX.EMBED_TEXT_1024('voyage-multimodal-3', %s)::VECTOR(FLOAT, 1024)
                    ) AS similarity
                FROM SECSIGNAL.RAW.IMAGE_EMBEDDINGS ie
                JOIN SECSIGNAL.RAW.FILING_IMAGES fi ON ie.IMAGE_ID = fi.IMAGE_ID
                ORDER BY similarity DESC
                LIMIT %s
                """,
                (query, limit),
            )
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            cursor.close()

    def _insert_text_corpus(self, chunks: list[dict[str, Any]]) -> None:
        """Insert text chunks into SEARCH_CORPUS for Cortex Search."""
        cursor = self._conn.cursor()
        try:
            for chunk in chunks:
                corpus_id = f"corpus_txt_{uuid.uuid4().hex[:12]}"
                cursor.execute(
                    """
                    INSERT INTO SECSIGNAL.RAW.SEARCH_CORPUS
                        (CORPUS_ID, FILING_ID, TICKER, FILING_TYPE, FILING_DATE,
                         CONTENT_TYPE, CONTENT, SOURCE_ID, SECTION_KEY)
                    VALUES (%s, %s, %s, %s, %s, 'text_chunk', %s, %s, %s)
                    """,
                    (
                        corpus_id,
                        chunk["filing_id"],
                        chunk.get("ticker"),
                        chunk.get("filing_type"),
                        chunk.get("filing_date"),
                        chunk["text"],
                        chunk.get("chunk_id", corpus_id),
                        chunk.get("section_key"),
                    ),
                )
        finally:
            cursor.close()

    def _insert_image_corpus(
        self,
        images: list[ExtractedImage],
        descriptions: dict[str, str],
        filing_metadata: dict[str, Any],
    ) -> None:
        """Insert chart descriptions into SEARCH_CORPUS for Cortex Search."""
        cursor = self._conn.cursor()
        try:
            for img in images:
                desc = descriptions.get(img.image_id)
                if not desc:
                    continue
                corpus_id = f"corpus_img_{uuid.uuid4().hex[:12]}"
                cursor.execute(
                    """
                    INSERT INTO SECSIGNAL.RAW.SEARCH_CORPUS
                        (CORPUS_ID, FILING_ID, TICKER, FILING_TYPE, FILING_DATE,
                         CONTENT_TYPE, CONTENT, SOURCE_ID, SECTION_KEY)
                    VALUES (%s, %s, %s, %s, %s, 'chart_description', %s, %s, NULL)
                    """,
                    (
                        corpus_id,
                        img.filing_id,
                        filing_metadata.get("ticker"),
                        filing_metadata.get("filing_type"),
                        filing_metadata.get("filing_date"),
                        desc,
                        img.image_id,
                    ),
                )
        finally:
            cursor.close()
