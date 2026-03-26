"""Extract and store chart/graph images from AI_PARSE_DOCUMENT output."""

from __future__ import annotations

import base64
import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

import structlog

from secsignal.processing.document_parser import ParsedDocument, ParsedElement

logger = structlog.get_logger(__name__)


@dataclass
class ExtractedImage:
    """A chart/graph image extracted from a filing."""

    image_id: str
    filing_id: str
    image_index: int
    image_data_b64: str
    image_format: str  # png, jpeg
    page_number: int
    bounding_box: dict[str, Any] | None
    size_bytes: int


class ImageExtractor:
    """Extract base64 images from parsed documents and persist to Snowflake.

    Filters for chart/graph images (skips logos, decorative elements) and
    stores them both as base64 in the FILING_IMAGES table and as files on
    the FILING_IMAGES_STAGE for downstream processing.
    """

    # Minimum image size to consider (skip tiny icons/logos)
    MIN_IMAGE_SIZE_BYTES = 5_000

    def __init__(self, snowflake_connection: Any) -> None:
        self._conn = snowflake_connection

    def extract_images(self, parsed_doc: ParsedDocument) -> list[ExtractedImage]:
        """Extract chart/graph images from a parsed document.

        Args:
            parsed_doc: Output from DocumentParser.

        Returns:
            List of ExtractedImage objects for images that pass filtering.
        """
        images: list[ExtractedImage] = []

        for i, element in enumerate(parsed_doc.image_elements):
            image_data = element.content
            if not image_data:
                continue

            # Decode to check size
            try:
                raw_bytes = base64.b64decode(image_data)
            except Exception:
                logger.warning("invalid_base64", filing_id=parsed_doc.filing_id, index=i)
                continue

            if len(raw_bytes) < self.MIN_IMAGE_SIZE_BYTES:
                logger.debug("skipping_small_image", size=len(raw_bytes), index=i)
                continue

            image_format = self._detect_format(raw_bytes)
            image_id = self._generate_image_id(parsed_doc.filing_id, i)

            images.append(
                ExtractedImage(
                    image_id=image_id,
                    filing_id=parsed_doc.filing_id,
                    image_index=i,
                    image_data_b64=image_data,
                    image_format=image_format,
                    page_number=element.page_number,
                    bounding_box=element.bounding_box,
                    size_bytes=len(raw_bytes),
                )
            )

        logger.info(
            "extracted_images",
            filing_id=parsed_doc.filing_id,
            total_image_elements=len(parsed_doc.image_elements),
            kept=len(images),
        )
        return images

    def store_images(self, images: list[ExtractedImage]) -> int:
        """Insert extracted images into the FILING_IMAGES table.

        Args:
            images: List of ExtractedImage objects.

        Returns:
            Number of rows inserted.
        """
        if not images:
            return 0

        cursor = self._conn.cursor()
        try:
            for img in images:
                cursor.execute(
                    """
                    INSERT INTO SECSIGNAL.RAW.FILING_IMAGES
                        (IMAGE_ID, FILING_ID, IMAGE_INDEX, IMAGE_DATA_B64,
                         IMAGE_FORMAT, PAGE_NUMBER, BOUNDING_BOX)
                    SELECT
                        %s, %s, %s, %s, %s, %s,
                        PARSE_JSON(%s)
                    """,
                    (
                        img.image_id,
                        img.filing_id,
                        img.image_index,
                        img.image_data_b64,
                        img.image_format,
                        img.page_number,
                        _bbox_to_json(img.bounding_box),
                    ),
                )
            return len(images)
        finally:
            cursor.close()

    @staticmethod
    def _detect_format(raw_bytes: bytes) -> str:
        """Detect image format from magic bytes."""
        if raw_bytes[:8] == b"\x89PNG\r\n\x1a\n":
            return "png"
        if raw_bytes[:2] == b"\xff\xd8":
            return "jpeg"
        return "unknown"

    @staticmethod
    def _generate_image_id(filing_id: str, index: int) -> str:
        """Generate a deterministic image ID."""
        content = f"{filing_id}:{index}"
        hash_prefix = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"img_{hash_prefix}"


def _bbox_to_json(bbox: dict[str, Any] | None) -> str:
    """Convert bounding box dict to JSON string, or NULL."""
    if bbox is None:
        return "null"
    import json

    return json.dumps(bbox)
