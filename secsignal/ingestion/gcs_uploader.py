"""Upload raw SEC filings to Google Cloud Storage with date-partitioned paths."""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Lazy import to avoid hard dependency when running outside GCP
_storage_client = None


def _get_storage_client() -> Any:
    """Lazily initialize the GCS storage client."""
    global _storage_client
    if _storage_client is None:
        from google.cloud import storage

        _storage_client = storage.Client()
    return _storage_client


class GCSUploader:
    """Upload filing documents to GCS with structured paths.

    Path format: gs://<bucket>/<filing_type>/<ticker>/<year>/<accession_number>/<filename>
    """

    def __init__(self, bucket_name: str) -> None:
        self._bucket_name = bucket_name

    def _get_bucket(self) -> Any:
        client = _get_storage_client()
        return client.bucket(self._bucket_name)

    def build_gcs_path(
        self,
        ticker: str,
        filing_type: str,
        filing_date: str,
        accession_number: str,
        filename: str,
    ) -> str:
        """Build a date-partitioned GCS path.

        Example: 10-K/AAPL/2024/0000320193-24-000123/filing.htm
        """
        year = filing_date[:4]
        return f"{filing_type}/{ticker.upper()}/{year}/{accession_number}/{filename}"

    def upload_bytes(
        self,
        data: bytes,
        gcs_path: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload raw bytes to GCS.

        Args:
            data: Raw file content.
            gcs_path: Destination path within the bucket.
            content_type: MIME type of the uploaded file.

        Returns:
            Full GCS URI (gs://bucket/path).
        """
        bucket = self._get_bucket()
        blob = bucket.blob(gcs_path)
        blob.upload_from_string(data, content_type=content_type)

        uri = f"gs://{self._bucket_name}/{gcs_path}"
        logger.info("uploaded_to_gcs", path=uri, size_bytes=len(data))
        return uri

    def upload_filing(
        self,
        data: bytes,
        ticker: str,
        filing_type: str,
        filing_date: str,
        accession_number: str,
        filename: str,
        content_type: str | None = None,
    ) -> str:
        """Upload a filing document with auto-generated path.

        Args:
            data: Raw document bytes.
            ticker: Stock ticker symbol.
            filing_type: e.g. '10-K', '10-Q'.
            filing_date: Filing date in YYYY-MM-DD format.
            accession_number: SEC accession number.
            filename: Original filename (e.g. 'filing.htm').
            content_type: Optional MIME type; inferred from extension if None.

        Returns:
            Full GCS URI.
        """
        if content_type is None:
            content_type = self._infer_content_type(filename)

        gcs_path = self.build_gcs_path(ticker, filing_type, filing_date, accession_number, filename)
        return self.upload_bytes(data, gcs_path, content_type)

    def file_exists(self, gcs_path: str) -> bool:
        """Check if a file already exists in GCS (to avoid re-uploads)."""
        bucket = self._get_bucket()
        blob = bucket.blob(gcs_path)
        return blob.exists()

    @staticmethod
    def _infer_content_type(filename: str) -> str:
        """Infer MIME type from file extension."""
        ext = filename.rsplit(".", maxsplit=1)[-1].lower() if "." in filename else ""
        return {
            "htm": "text/html",
            "html": "text/html",
            "xml": "application/xml",
            "xbrl": "application/xml",
            "json": "application/json",
            "txt": "text/plain",
            "pdf": "application/pdf",
        }.get(ext, "application/octet-stream")
