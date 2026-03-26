"""Parse filing PDFs using Snowflake Cortex AI_PARSE_DOCUMENT.

Uses LAYOUT mode with image extraction to get both structured text and
embedded charts/graphs as base64 images.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ParsedElement:
    """A single element extracted from a document."""

    element_type: str  # 'text', 'table', 'heading', 'image'
    content: str  # text content or base64 image data
    page_number: int
    index: int
    bounding_box: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedDocument:
    """Full result of parsing a document with AI_PARSE_DOCUMENT."""

    filing_id: str
    elements: list[ParsedElement]
    text_elements: list[ParsedElement]
    image_elements: list[ParsedElement]
    page_count: int
    raw_response: dict[str, Any]


class DocumentParser:
    """Parse SEC filing PDFs via Snowflake Cortex AI_PARSE_DOCUMENT.

    Executes AI_PARSE_DOCUMENT in LAYOUT mode with extract_images=true to get
    both structured text content and embedded chart/graph images.
    """

    def __init__(self, snowflake_connection: Any) -> None:
        """Initialize with a Snowflake connection.

        Args:
            snowflake_connection: Active snowflake.connector connection or
                                 snowpark Session.
        """
        self._conn = snowflake_connection

    def parse_from_stage(self, stage_path: str, filing_id: str) -> ParsedDocument:
        """Parse a PDF document from a Snowflake stage.

        Args:
            stage_path: Full stage path, e.g. '@FILING_DOCUMENTS_STAGE/path/to/filing.pdf'
            filing_id: Accession number for tracking.

        Returns:
            ParsedDocument with text and image elements.
        """
        # AI_PARSE_DOCUMENT with LAYOUT mode extracts spatial layout + images
        query = f"""
            SELECT SNOWFLAKE.CORTEX.AI_PARSE_DOCUMENT(
                BUILD_SCOPED_FILE_URL('{stage_path}'),
                {{
                    'mode': 'LAYOUT',
                    'extract_images': true
                }}
            ) AS parsed_result
        """

        cursor = self._conn.cursor()
        try:
            cursor.execute(query)
            row = cursor.fetchone()
            if row is None:
                logger.warning("ai_parse_document_empty", filing_id=filing_id)
                return ParsedDocument(
                    filing_id=filing_id,
                    elements=[],
                    text_elements=[],
                    image_elements=[],
                    page_count=0,
                    raw_response={},
                )

            import json

            raw_response = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        finally:
            cursor.close()

        return self._parse_response(raw_response, filing_id)

    def _parse_response(self, response: dict[str, Any], filing_id: str) -> ParsedDocument:
        """Convert AI_PARSE_DOCUMENT JSON response into structured ParsedDocument."""
        elements: list[ParsedElement] = []
        text_elements: list[ParsedElement] = []
        image_elements: list[ParsedElement] = []

        pages = response.get("pages", [])
        index = 0

        for page_num, page in enumerate(pages, start=1):
            for block in page.get("blocks", []):
                block_type = block.get("type", "text").lower()
                content = block.get("text", "") or block.get("image", "")
                bbox = block.get("boundingBox")

                element = ParsedElement(
                    element_type=block_type,
                    content=content,
                    page_number=page_num,
                    index=index,
                    bounding_box=bbox,
                    metadata={"block_id": block.get("id", str(uuid.uuid4()))},
                )
                elements.append(element)
                index += 1

                if block_type == "image" and content:
                    image_elements.append(element)
                elif content.strip():
                    text_elements.append(element)

        logger.info(
            "parsed_document",
            filing_id=filing_id,
            pages=len(pages),
            text_blocks=len(text_elements),
            images=len(image_elements),
        )

        return ParsedDocument(
            filing_id=filing_id,
            elements=elements,
            text_elements=text_elements,
            image_elements=image_elements,
            page_count=len(pages),
            raw_response=response,
        )
