"""Re-parse existing filings from GCS using the fixed parser.

Reads HTML from GCS, parses with the updated FilingParser, and inserts
sections into RAW_FILING_SECTIONS.  Does NOT re-download from EDGAR.

Usage:
    python scripts/reparse_filings.py
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

from secsignal.ingestion.filing_parser import FilingParser

load_dotenv(PROJECT_ROOT / ".env")


def main() -> None:
    conn = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        role=os.environ["SNOWFLAKE_ROLE"],
    )

    # Fetch filings to re-parse
    cur = conn.cursor()
    cur.execute(
        "SELECT FILING_ID, TICKER, FILING_TYPE, GCS_URI FROM SECSIGNAL.RAW.RAW_FILINGS"
    )
    filings = cur.fetchall()
    cur.close()

    gcs_client = storage.Client()
    parser = FilingParser()
    total_sections = 0

    for filing_id, ticker, filing_type, gcs_uri in filings:
        print(f"\n--- {ticker} {filing_type} ({filing_id}) ---")

        # Download HTML from GCS
        # gcs_uri format: gs://bucket/path
        parts = gcs_uri.replace("gs://", "").split("/", 1)
        bucket_name, blob_path = parts[0], parts[1]
        bucket = gcs_client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        html_bytes = blob.download_as_bytes()
        print(f"  Downloaded {len(html_bytes):,} bytes from GCS")

        # Parse with fixed parser
        parsed = parser.parse_html(html_bytes, filing_id, filing_type)
        print(f"  Parsed {len(parsed.sections)} sections:")
        for sec in parsed.sections:
            print(f"    {sec.section.value}: {sec.word_count} words ({len(sec.text)} chars) - {sec.title[:60]}")

        # Insert into RAW_FILING_SECTIONS
        cur = conn.cursor()
        inserted = 0
        for sec in parsed.sections:
            section_id = f"{filing_id}_{sec.section.value}"
            cur.execute(
                "SELECT 1 FROM SECSIGNAL.RAW.RAW_FILING_SECTIONS WHERE SECTION_ID = %s",
                (section_id,),
            )
            if cur.fetchone():
                continue
            cur.execute(
                """
                INSERT INTO SECSIGNAL.RAW.RAW_FILING_SECTIONS
                    (SECTION_ID, FILING_ID, SECTION_KEY, SECTION_TITLE,
                     SECTION_TEXT, WORD_COUNT, START_OFFSET, END_OFFSET)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    section_id,
                    filing_id,
                    sec.section.value,
                    sec.title,
                    sec.text,
                    sec.word_count,
                    sec.start_offset,
                    sec.end_offset,
                ),
            )
            inserted += 1
        cur.close()
        total_sections += inserted
        print(f"  Inserted {inserted} sections into RAW_FILING_SECTIONS")

    conn.close()
    print(f"\nDone. Total sections inserted: {total_sections}")


if __name__ == "__main__":
    main()
