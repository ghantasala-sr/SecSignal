"""Generate natural language descriptions for chart images using Cortex AI_COMPLETE.

Uses multimodal LLM models (e.g., Claude, LLaMA) to produce rich text descriptions
of charts that can be indexed for semantic search alongside filing text.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from secsignal.processing.image_extractor import ExtractedImage

logger = structlog.get_logger(__name__)

# Default model for chart description — multimodal capable
DEFAULT_MODEL = "mistral-large2"

DESCRIPTION_PROMPT = """Analyze this chart/graph from an SEC filing and provide a detailed description.

Include:
1. Chart type (bar chart, pie chart, line graph, etc.)
2. What data is being visualized (metrics, time periods, categories)
3. Key trends or patterns visible
4. Notable data points (highest, lowest, outliers)
5. Any labels, legends, or annotations visible

Be factual and specific. Reference actual values where visible.
Keep the description under 500 words."""


class DescriptionGenerator:
    """Generate text descriptions for chart images using Cortex AI_COMPLETE.

    Descriptions are used for:
    - Semantic search indexing (Cortex Search)
    - Cross-modal retrieval context
    - Answer synthesis by the agent layer
    """

    def __init__(self, snowflake_connection: Any, model: str = DEFAULT_MODEL) -> None:
        self._conn = snowflake_connection
        self._model = model

    def generate_description(self, image: ExtractedImage) -> str | None:
        """Generate a text description for a chart image.

        Args:
            image: ExtractedImage with base64-encoded chart.

        Returns:
            Text description string, or None if generation fails.
        """
        data_uri = f"data:image/{image.image_format};base64,{image.image_data_b64}"

        # AI_COMPLETE with multimodal input: text prompt + image
        query = """
            SELECT SNOWFLAKE.CORTEX.AI_COMPLETE(
                %s,
                [
                    {
                        'role': 'user',
                        'content': [
                            {'type': 'text', 'text': %s},
                            {'type': 'image_url', 'image_url': {'url': %s}}
                        ]
                    }
                ],
                {'temperature': 0.1, 'max_tokens': 800}
            ) AS description
        """

        cursor = self._conn.cursor()
        try:
            cursor.execute(query, (self._model, DESCRIPTION_PROMPT, data_uri))
            row = cursor.fetchone()
            if row is None:
                return None

            result = json.loads(row[0]) if isinstance(row[0], str) else row[0]

            # AI_COMPLETE returns {"choices": [{"messages": "..."}]}
            description = ""
            if isinstance(result, dict):
                choices = result.get("choices", [])
                if choices:
                    description = choices[0].get("messages", "") or choices[0].get("message", {}).get("content", "")
            elif isinstance(result, str):
                description = result

            if description:
                logger.info(
                    "generated_description",
                    image_id=image.image_id,
                    length=len(description),
                )
            return description or None

        except Exception:
            logger.exception("description_generation_failed", image_id=image.image_id)
            return None
        finally:
            cursor.close()

    def generate_batch(self, images: list[ExtractedImage]) -> dict[str, str]:
        """Generate descriptions for multiple images.

        Args:
            images: List of ExtractedImage objects.

        Returns:
            Dict mapping image_id → description text.
        """
        descriptions: dict[str, str] = {}
        for image in images:
            desc = self.generate_description(image)
            if desc:
                descriptions[image.image_id] = desc

        logger.info(
            "description_batch",
            total=len(images),
            successful=len(descriptions),
        )
        return descriptions

    def update_image_descriptions(self, descriptions: dict[str, str]) -> int:
        """Update FILING_IMAGES table with generated descriptions.

        Returns:
            Number of rows updated.
        """
        if not descriptions:
            return 0

        cursor = self._conn.cursor()
        updated = 0
        try:
            for image_id, description in descriptions.items():
                cursor.execute(
                    """
                    UPDATE SECSIGNAL.RAW.FILING_IMAGES
                    SET DESCRIPTION = %s
                    WHERE IMAGE_ID = %s
                    """,
                    (description, image_id),
                )
                updated += cursor.rowcount
            return updated
        finally:
            cursor.close()
