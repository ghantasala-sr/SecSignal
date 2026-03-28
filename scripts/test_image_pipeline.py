"""Test the image pipeline on existing filings.

Downloads HTML from GCS, parses <img> tags, downloads images from EDGAR,
stores in FILING_IMAGES, analyzes charts with AI_EXTRACT → CHART_EXTRACTS.

Usage:
    python scripts/test_image_pipeline.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import snowflake.connector
from dotenv import load_dotenv
from google.cloud import storage

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from secsignal.processing.image_extractor import ImageExtractor
from secsignal.processing.chart_analyzer import ChartAnalyzer

load_dotenv(PROJECT_ROOT / ".env")

# EDGAR document base URLs for our filings
FILING_DOC_URLS = {
    "0000320193-25-000079": "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm",
    "0000320193-26-000006": "https://www.sec.gov/Archives/edgar/data/320193/000032019326000006/aapl-20251227.htm",
}


def main() -> None:
    conn = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        role=os.environ["SNOWFLAKE_ROLE"],
    )

    # Fetch filings
    cur = conn.cursor()
    cur.execute(
        "SELECT FILING_ID, TICKER, FILING_TYPE, FILING_DATE, GCS_URI "
        "FROM SECSIGNAL.RAW.RAW_FILINGS"
    )
    filings = cur.fetchall()
    cur.close()

    gcs_client = storage.Client()
    total_images = 0
    total_extracts = 0
    user_agent = os.environ.get("EDGAR_USER_AGENT", "SecSignal agent@secsignal.dev")

    for filing_id, ticker, filing_type, filing_date, gcs_uri in filings:
        print(f"\n--- {ticker} {filing_type} ({filing_id}) ---")

        # Download HTML from GCS
        parts = gcs_uri.replace("gs://", "").split("/", 1)
        bucket = gcs_client.bucket(parts[0])
        blob = bucket.blob(parts[1])
        html_bytes = blob.download_as_bytes()
        print(f"  Downloaded {len(html_bytes):,} bytes from GCS")

        # Get EDGAR document URL for this filing
        document_url = FILING_DOC_URLS.get(filing_id, "")
        if not document_url:
            print(f"  No document URL for {filing_id}, skipping image extraction")
            continue

        # Extract images from HTML <img> tags
        print(f"  Extracting images from HTML (base URL: {document_url})...")
        extractor = ImageExtractor(conn)
        images = extractor.extract_images_from_html(
            html_bytes, filing_id, document_url, user_agent
        )

        if not images:
            print("  No images found (or all below 5KB threshold)")
            continue

        print(f"  Found {len(images)} images passing size filter")
        for img in images:
            print(f"    {img.image_id}: {img.image_format}, {img.size_bytes:,} bytes")

        # Store images in FILING_IMAGES
        stored = extractor.store_images(images)
        total_images += stored
        print(f"  Stored {stored} images in FILING_IMAGES")

        # Analyze charts with AI_EXTRACT
        print(f"  Analyzing {len(images)} images with AI_EXTRACT...")
        analyzer = ChartAnalyzer(conn)
        extracts = analyzer.analyze_batch(images)
        if extracts:
            stored = analyzer.store_extracts(extracts)
            total_extracts += stored
            print(f"  Stored {stored} chart extracts in CHART_EXTRACTS")
            for ext in extracts:
                print(f"    {ext.chart_type}: {ext.chart_title} ({ext.data_points} data points)")
        else:
            print("  No chart data extracted (images may not be charts)")

    conn.close()
    print(f"\nDone. Total images: {total_images}, chart extracts: {total_extracts}")


if __name__ == "__main__":
    main()
