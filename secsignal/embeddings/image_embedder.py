"""Image embedding using Snowflake Cortex EMBED_TEXT_1024 with voyage-multimodal-3.

Produces cross-modal embeddings that allow text queries to match chart images
and vice versa. Both text and images are mapped to the same vector space.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from secsignal.processing.image_extractor import ExtractedImage

logger = structlog.get_logger(__name__)

MODEL = "voyage-multimodal-3"
EMBEDDING_DIM = 1024  # voyage-multimodal-3 output dimension


class ImageEmbedder:
    """Embed chart images using Cortex EMBED_TEXT_1024 with voyage-multimodal-3.

    Creates cross-modal vectors in the same space as text, enabling:
    - Text query → chart image retrieval
    - Chart image → similar text retrieval
    """

    def __init__(self, snowflake_connection: Any, model: str = MODEL) -> None:
        self._conn = snowflake_connection
        self._model = model

    def embed_image(self, image: ExtractedImage) -> list[float] | None:
        """Embed a single image using its base64 data.

        Args:
            image: ExtractedImage with base64-encoded chart data.

        Returns:
            Embedding vector (1024 dims), or None on error.
        """
        data_uri = f"data:image/{image.image_format};base64,{image.image_data_b64}"

        cursor = self._conn.cursor()
        try:
            cursor.execute(
                "SELECT SNOWFLAKE.CORTEX.EMBED_TEXT_1024(%s, %s)::VECTOR(FLOAT, 1024) AS emb",
                (self._model, data_uri),
            )
            row = cursor.fetchone()
            return row[0] if row else None
        except Exception:
            logger.exception("image_embed_failed", image_id=image.image_id)
            return None
        finally:
            cursor.close()

    def embed_text_for_cross_modal(self, text: str) -> list[float] | None:
        """Embed a text query in the same cross-modal space as images.

        This allows text queries to retrieve matching chart images.

        Args:
            text: Query text to embed.

        Returns:
            Embedding vector in the same space as image embeddings.
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
            logger.exception("cross_modal_text_embed_failed", text_len=len(text))
            return None
        finally:
            cursor.close()

    def embed_and_store_images(
        self,
        images: list[ExtractedImage],
        descriptions: dict[str, str] | None = None,
        filing_metadata: dict[str, Any] | None = None,
    ) -> int:
        """Embed images and insert into IMAGE_EMBEDDINGS table.

        Args:
            images: List of ExtractedImage objects.
            descriptions: Optional dict mapping image_id → description text.
            filing_metadata: Optional dict with ticker, filing_type, filing_date.

        Returns:
            Number of rows inserted.
        """
        if not images:
            return 0

        metadata = filing_metadata or {}
        descs = descriptions or {}

        cursor = self._conn.cursor()
        inserted = 0
        try:
            for img in images:
                data_uri = f"data:image/{img.image_format};base64,{img.image_data_b64}"
                embedding_id = f"emb_{uuid.uuid4().hex[:12]}"

                cursor.execute(
                    """
                    INSERT INTO SECSIGNAL.RAW.IMAGE_EMBEDDINGS
                        (EMBEDDING_ID, IMAGE_ID, FILING_ID, TICKER, FILING_TYPE,
                         FILING_DATE, CHART_TYPE, DESCRIPTION, EMBEDDING)
                    SELECT
                        %s, %s, %s, %s, %s, %s, %s, %s,
                        SNOWFLAKE.CORTEX.EMBED_TEXT_1024(%s, %s)::VECTOR(FLOAT, 1024)
                    """,
                    (
                        embedding_id,
                        img.image_id,
                        img.filing_id,
                        metadata.get("ticker"),
                        metadata.get("filing_type"),
                        metadata.get("filing_date"),
                        None,  # chart_type set later from chart_analyzer
                        descs.get(img.image_id),
                        self._model,
                        data_uri,
                    ),
                )
                inserted += 1

            logger.info("image_embedding_batch", total=len(images), inserted=inserted)
            return inserted
        finally:
            cursor.close()
