"""Analyze chart images using Snowflake Cortex AI_EXTRACT.

AI_EXTRACT uses a vision-language model (Arctic-Extract) to extract structured
data from charts without OCR — it understands the visual content directly.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import structlog

from secsignal.processing.image_extractor import ExtractedImage

logger = structlog.get_logger(__name__)


@dataclass
class ChartExtract:
    """Structured data extracted from a chart image."""

    extract_id: str
    image_id: str
    filing_id: str
    chart_type: str  # bar, pie, line, area, table
    chart_title: str
    extracted_data: dict[str, Any]
    data_points: int
    confidence_score: float


class ChartAnalyzer:
    """Extract structured data from filing charts using Cortex AI_EXTRACT.

    For each chart image, AI_EXTRACT returns structured JSON with data
    values, labels, and chart metadata — no OCR needed.
    """

    def __init__(self, snowflake_connection: Any) -> None:
        self._conn = snowflake_connection

    def analyze_chart(self, image: ExtractedImage) -> ChartExtract | None:
        """Extract structured data from a single chart image.

        Args:
            image: ExtractedImage with base64-encoded chart.

        Returns:
            ChartExtract with structured data, or None if extraction fails.
        """
        # AI_EXTRACT accepts base64 image inline via a data URI
        query = """
            SELECT SNOWFLAKE.CORTEX.AI_EXTRACT(
                %s,
                {
                    'chart_type': 'string: type of chart (bar, pie, line, area, table, other)',
                    'chart_title': 'string: title or caption of the chart',
                    'x_axis_label': 'string: label of the x-axis if applicable',
                    'y_axis_label': 'string: label of the y-axis if applicable',
                    'data_series': 'array: list of data series with name, values, and labels',
                    'data_points_count': 'integer: total number of data points',
                    'currency': 'string: currency if financial data (USD, EUR, etc.)',
                    'time_period': 'string: time period covered by the chart'
                }
            ) AS extract_result
        """

        data_uri = f"data:image/{image.image_format};base64,{image.image_data_b64}"

        cursor = self._conn.cursor()
        try:
            cursor.execute(query, (data_uri,))
            row = cursor.fetchone()
            if row is None:
                return None

            result = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        except Exception:
            logger.exception("ai_extract_failed", image_id=image.image_id)
            return None
        finally:
            cursor.close()

        return self._build_extract(result, image)

    def analyze_batch(self, images: list[ExtractedImage]) -> list[ChartExtract]:
        """Analyze multiple chart images and return successful extracts."""
        extracts: list[ChartExtract] = []
        for image in images:
            extract = self.analyze_chart(image)
            if extract is not None:
                extracts.append(extract)
        logger.info("chart_analysis_batch", total=len(images), successful=len(extracts))
        return extracts

    def store_extracts(self, extracts: list[ChartExtract]) -> int:
        """Insert chart extracts into CHART_EXTRACTS table.

        Returns:
            Number of rows inserted.
        """
        if not extracts:
            return 0

        cursor = self._conn.cursor()
        inserted = 0
        try:
            for ext in extracts:
                # Skip if already stored (idempotent re-runs)
                cursor.execute(
                    "SELECT 1 FROM SECSIGNAL.RAW.CHART_EXTRACTS WHERE IMAGE_ID = %s",
                    (ext.image_id,),
                )
                if cursor.fetchone():
                    continue
                cursor.execute(
                    """
                    INSERT INTO SECSIGNAL.RAW.CHART_EXTRACTS
                        (EXTRACT_ID, IMAGE_ID, FILING_ID, CHART_TYPE,
                         CHART_TITLE, EXTRACTED_DATA, DATA_POINTS, CONFIDENCE_SCORE)
                    SELECT %s, %s, %s, %s, %s, PARSE_JSON(%s), %s, %s
                    """,
                    (
                        ext.extract_id,
                        ext.image_id,
                        ext.filing_id,
                        ext.chart_type,
                        ext.chart_title,
                        json.dumps(ext.extracted_data),
                        ext.data_points,
                        ext.confidence_score,
                    ),
                )
                inserted += 1
            return inserted
        finally:
            cursor.close()

    def _build_extract(self, result: dict[str, Any], image: ExtractedImage) -> ChartExtract:
        """Build a ChartExtract from AI_EXTRACT response."""
        data_series = result.get("data_series", [])
        data_points = result.get("data_points_count", 0)
        if isinstance(data_series, list):
            data_points = max(data_points, sum(len(s.get("values", [])) for s in data_series))

        return ChartExtract(
            extract_id=f"ext_{uuid.uuid4().hex[:12]}",
            image_id=image.image_id,
            filing_id=image.filing_id,
            chart_type=result.get("chart_type", "unknown"),
            chart_title=result.get("chart_title", ""),
            extracted_data=result,
            data_points=data_points,
            confidence_score=result.get("confidence_score", 0.0),
        )
