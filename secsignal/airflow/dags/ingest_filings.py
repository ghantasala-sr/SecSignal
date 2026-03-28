"""SecSignal EDGAR ingestion DAG — fetches filings, uploads to GCS,
parses HTML, stores sections, runs dbt quality checks, and embeds text.

Schedule: Weekly on Sundays at 06:00 UTC (SEC filings land on business days).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

# ---------------------------------------------------------------------------
# DAG-level config
# ---------------------------------------------------------------------------
DEFAULT_TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]
MAX_FILINGS_PER_COMPANY = 5

default_args = {
    "owner": "secsignal",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(hours=2),
}


# ---------------------------------------------------------------------------
# Task callables — thin wrappers around pipeline logic
# ---------------------------------------------------------------------------
def fetch_metadata(**context):
    """Resolve tickers → CIKs, fetch filing metadata from EDGAR."""
    import asyncio
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[3] / ".env")

    from secsignal.ingestion.edgar_client import EdgarClient

    tickers = context["params"].get("tickers", DEFAULT_TICKERS)
    max_filings = context["params"].get("max_filings", MAX_FILINGS_PER_COMPANY)
    user_agent = os.environ.get("EDGAR_USER_AGENT", "SecSignal agent@secsignal.dev")

    async def _fetch():
        results = {}
        async with EdgarClient(user_agent=user_agent) as client:
            for ticker in tickers:
                cik = await client.get_cik_for_ticker(ticker)
                if not cik:
                    continue
                filings = await client.get_company_filings(
                    cik=cik, filing_types=("10-K", "10-Q"), max_filings=max_filings,
                )
                results[ticker] = [
                    {
                        "accession_number": f.accession_number,
                        "cik": f.cik,
                        "company_name": f.company_name,
                        "ticker": f.ticker,
                        "filing_type": f.filing_type,
                        "filing_date": f.filing_date,
                        "primary_document": f.primary_document,
                        "primary_doc_url": f.primary_doc_url,
                        "filing_index_url": f.filing_index_url,
                    }
                    for f in filings
                ]
        return results

    ticker_filings = asyncio.run(_fetch())
    context["ti"].xcom_push(key="ticker_filings", value=ticker_filings)
    total = sum(len(v) for v in ticker_filings.values())
    print(f"Fetched metadata for {len(ticker_filings)} companies, {total} filings")


def process_filings(**context):
    """Download HTML, upload to GCS, parse sections, store in Snowflake."""
    import asyncio
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[3] / ".env")

    import snowflake.connector

    from secsignal.ingestion.edgar_client import EdgarClient, Filing
    from secsignal.ingestion.filing_parser import FilingParser
    from secsignal.ingestion.gcs_uploader import GCSUploader

    ticker_filings = context["ti"].xcom_pull(key="ticker_filings", task_ids="fetch_metadata")
    user_agent = os.environ.get("EDGAR_USER_AGENT", "SecSignal agent@secsignal.dev")
    gcs_bucket = os.environ.get("GCS_BUCKET", "secsignal-raw")

    conn = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        role=os.environ["SNOWFLAKE_ROLE"],
    )
    uploader = GCSUploader(bucket_name=gcs_bucket)
    parser = FilingParser()

    filings_processed = 0
    sections_stored = 0

    try:
        for ticker, filings_data in ticker_filings.items():
            if not filings_data:
                continue

            sample = filings_data[0]
            _upsert_company(conn, sample["cik"], sample["ticker"], sample["company_name"])

            for fd in filings_data:
                filing = Filing(**fd, metadata={})
                try:
                    html_bytes = asyncio.run(_download(filing.primary_doc_url, user_agent))

                    gcs_uri = uploader.upload_filing(
                        data=html_bytes, ticker=ticker, filing_type=filing.filing_type,
                        filing_date=filing.filing_date, accession_number=filing.accession_number,
                        filename=filing.primary_document,
                    )

                    _upsert_filing(conn, filing, gcs_uri, len(html_bytes))
                    filings_processed += 1

                    parsed = parser.parse_html(html_bytes, filing.accession_number, filing.filing_type)
                    sections_stored += _insert_sections(conn, filing.accession_number, parsed.sections)

                except Exception as e:
                    print(f"Failed processing {filing.accession_number}: {e}")
                    continue
    finally:
        conn.close()

    print(f"Processed {filings_processed} filings, stored {sections_stored} sections")


def process_images(**context):
    """Run image pipeline: parse HTML <img> tags → download from EDGAR → analyze charts."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[3] / ".env")

    import snowflake.connector

    from secsignal.processing.image_extractor import ImageExtractor
    from secsignal.processing.chart_analyzer import ChartAnalyzer

    conn = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        role=os.environ["SNOWFLAKE_ROLE"],
    )

    total_images = 0
    total_extracts = 0

    try:
        # Get filings that don't have images yet
        cur = conn.cursor()
        cur.execute("""
            SELECT f.FILING_ID, f.GCS_URI, f.DOCUMENT_URL
            FROM SECSIGNAL.RAW.RAW_FILINGS f
            WHERE f.GCS_URI IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM SECSIGNAL.RAW.FILING_IMAGES fi
                  WHERE fi.FILING_ID = f.FILING_ID
              )
        """)
        filings = cur.fetchall()
        cur.close()

        if not filings:
            print("No new filings to process for images")
            return

        from google.cloud import storage as gcs_storage
        gcs_client = gcs_storage.Client()
        user_agent = os.environ.get("EDGAR_USER_AGENT", "SecSignal agent@secsignal.dev")

        for filing_id, gcs_uri, document_url in filings:
            try:
                # Download HTML from GCS
                parts = gcs_uri.replace("gs://", "").split("/", 1)
                bucket = gcs_client.bucket(parts[0])
                blob = bucket.blob(parts[1])
                html_bytes = blob.download_as_bytes()

                # Extract images from HTML <img> tags
                extractor = ImageExtractor(conn)
                images = extractor.extract_images_from_html(
                    html_bytes, filing_id, document_url or "", user_agent
                )

                if not images:
                    print(f"No images in {filing_id}")
                    continue

                total_images += extractor.store_images(images)

                # Analyze charts with AI_EXTRACT
                analyzer = ChartAnalyzer(conn)
                extracts = analyzer.analyze_batch(images)
                if extracts:
                    total_extracts += analyzer.store_extracts(extracts)

            except Exception as e:
                print(f"Image pipeline failed for {filing_id}: {e}")
                continue
    finally:
        conn.close()

    print(f"Extracted {total_images} images, {total_extracts} chart extracts")


def embed_images(**context):
    """Embed chart images using voyage-multimodal-3 via Cortex EMBED_TEXT_1024."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[3] / ".env")

    import snowflake.connector

    from secsignal.embeddings.cortex_embed import CortexEmbedder
    from secsignal.processing.image_extractor import ExtractedImage

    conn = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        role=os.environ["SNOWFLAKE_ROLE"],
    )

    embedder = CortexEmbedder(conn)
    total_embedded = 0

    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT fi.IMAGE_ID, fi.FILING_ID, fi.IMAGE_INDEX,
                   fi.IMAGE_DATA_B64, fi.IMAGE_FORMAT, fi.PAGE_NUMBER,
                   fi.BOUNDING_BOX,
                   f.TICKER, f.FILING_TYPE, f.FILING_DATE,
                   ce.CHART_TITLE, ce.CHART_TYPE
            FROM SECSIGNAL.RAW.FILING_IMAGES fi
            JOIN SECSIGNAL.RAW.RAW_FILINGS f ON fi.FILING_ID = f.FILING_ID
            LEFT JOIN SECSIGNAL.RAW.CHART_EXTRACTS ce ON fi.IMAGE_ID = ce.IMAGE_ID
            WHERE NOT EXISTS (
                SELECT 1 FROM SECSIGNAL.RAW.IMAGE_EMBEDDINGS ie
                WHERE ie.IMAGE_ID = fi.IMAGE_ID
            )
        """)
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        image_data = [dict(zip(columns, row)) for row in rows]
        cur.close()

        if not image_data:
            print("No new images to embed")
            return

        from collections import defaultdict
        by_filing: dict[str, list] = defaultdict(list)
        for row in image_data:
            by_filing[row["FILING_ID"]].append(row)

        for fid, frows in by_filing.items():
            images = [
                ExtractedImage(
                    image_id=r["IMAGE_ID"],
                    filing_id=r["FILING_ID"],
                    image_index=r["IMAGE_INDEX"],
                    image_data_b64=r["IMAGE_DATA_B64"],
                    image_format=r["IMAGE_FORMAT"],
                    page_number=r["PAGE_NUMBER"],
                    bounding_box=r["BOUNDING_BOX"],
                    size_bytes=len(r["IMAGE_DATA_B64"]) * 3 // 4 if r["IMAGE_DATA_B64"] else 0,
                )
                for r in frows
            ]
            descriptions = {}
            metadata = {
                "ticker": frows[0]["TICKER"],
                "filing_type": frows[0]["FILING_TYPE"],
                "filing_date": frows[0]["FILING_DATE"],
            }
            for r in frows:
                title = r.get("CHART_TITLE") or f"Filing image from page {r['PAGE_NUMBER']}"
                ctype = r.get("CHART_TYPE") or "image"
                descriptions[r["IMAGE_ID"]] = f"{title} ({ctype})"

            total_embedded += embedder.embed_filing_images(images, descriptions, metadata)

    finally:
        conn.close()

    print(f"Embedded {total_embedded} images")


def run_dbt(**context):
    """Run dbt build to refresh staging → intermediate → marts with tests."""
    import subprocess
    import sys
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(project_root))
    from dotenv import load_dotenv

    load_dotenv(project_root / ".env")

    dbt_dir = project_root / "dbt"
    dbt_bin = project_root / ".venv" / "bin" / "dbt"

    if not dbt_bin.exists():
        raise FileNotFoundError(f"dbt not found at {dbt_bin}")

    result = subprocess.run(
        [str(dbt_bin), "build", "--profiles-dir", "."],
        cwd=str(dbt_dir),
        capture_output=True,
        text=True,
        env={**os.environ},
    )

    print(result.stdout[-2000:] if result.stdout else "")
    if result.returncode != 0:
        print(result.stderr[-2000:] if result.stderr else "")
        raise RuntimeError(f"dbt build failed with exit code {result.returncode}")

    print("dbt build completed successfully")


def embed_text(**context):
    """Embed text sections from validated INT_PARSED_SECTIONS using Cortex EMBED_TEXT_1024."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[3] / ".env")

    import snowflake.connector

    from secsignal.embeddings.cortex_embed import CortexEmbedder
    from secsignal.ingestion.filing_parser import chunk_text

    conn = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        role=os.environ["SNOWFLAKE_ROLE"],
    )

    embedder = CortexEmbedder(conn)
    total_embedded = 0

    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT s.FILING_ID, s.SECTION_KEY, s.SECTION_TEXT, s.WORD_COUNT,
                   s.TICKER, s.FILING_TYPE, s.FILING_DATE
            FROM SECSIGNAL.INTERMEDIATE.INT_PARSED_SECTIONS s
            WHERE s.WORD_COUNT > 20
              AND NOT EXISTS (
                  SELECT 1 FROM SECSIGNAL.RAW.TEXT_EMBEDDINGS e
                  WHERE e.FILING_ID = s.FILING_ID AND e.SECTION_KEY = s.SECTION_KEY
              )
        """)
        rows = cur.fetchall()
        cur.close()

        for filing_id, section_key, section_text, word_count, ticker, filing_type, filing_date in rows:
            text_chunks = chunk_text(section_text, 1500, 200)
            chunks = [
                {
                    "text": c,
                    "filing_id": filing_id,
                    "section_key": section_key,
                    "chunk_index": i,
                    "ticker": ticker,
                    "filing_type": filing_type,
                    "filing_date": str(filing_date),
                }
                for i, c in enumerate(text_chunks)
            ]
            if chunks:
                total_embedded += embedder.embed_filing_text(chunks)

    finally:
        conn.close()

    print(f"Embedded {total_embedded} text chunks")


# ---------------------------------------------------------------------------
# Helper functions (same logic as run_pipeline.py)
# ---------------------------------------------------------------------------
async def _download(url: str, user_agent: str) -> bytes:
    from secsignal.ingestion.edgar_client import EdgarClient

    async with EdgarClient(user_agent=user_agent) as client:
        return await client.download_filing_document(url)


def _upsert_company(conn, cik, ticker, company_name):
    cur = conn.cursor()
    try:
        cur.execute(
            """MERGE INTO SECSIGNAL.RAW.RAW_COMPANIES tgt
            USING (SELECT %s AS CIK, %s AS TICKER, %s AS COMPANY_NAME) src
            ON tgt.CIK = src.CIK
            WHEN MATCHED THEN UPDATE SET TICKER = src.TICKER, COMPANY_NAME = src.COMPANY_NAME, LOADED_AT = CURRENT_TIMESTAMP()
            WHEN NOT MATCHED THEN INSERT (CIK, TICKER, COMPANY_NAME) VALUES (src.CIK, src.TICKER, src.COMPANY_NAME)""",
            (cik, ticker, company_name),
        )
    finally:
        cur.close()


def _upsert_filing(conn, filing, gcs_uri, file_size):
    cur = conn.cursor()
    try:
        cur.execute(
            """MERGE INTO SECSIGNAL.RAW.RAW_FILINGS tgt
            USING (SELECT %s AS FILING_ID) src ON tgt.FILING_ID = src.FILING_ID
            WHEN NOT MATCHED THEN INSERT
                (FILING_ID, CIK, TICKER, FILING_TYPE, FILING_DATE, PRIMARY_DOCUMENT, DOCUMENT_URL, GCS_URI, FILE_SIZE_BYTES)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (filing.accession_number, filing.accession_number, filing.cik, filing.ticker,
             filing.filing_type, filing.filing_date, filing.primary_document,
             filing.primary_doc_url, gcs_uri, file_size),
        )
    finally:
        cur.close()


def _insert_sections(conn, filing_id, sections):
    cur = conn.cursor()
    inserted = 0
    try:
        for sec in sections:
            section_id = f"{filing_id}_{sec.section.value}"
            cur.execute("SELECT 1 FROM SECSIGNAL.RAW.RAW_FILING_SECTIONS WHERE SECTION_ID = %s", (section_id,))
            if cur.fetchone():
                continue
            cur.execute(
                """INSERT INTO SECSIGNAL.RAW.RAW_FILING_SECTIONS
                    (SECTION_ID, FILING_ID, SECTION_KEY, SECTION_TITLE, SECTION_TEXT, WORD_COUNT, START_OFFSET, END_OFFSET)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (section_id, filing_id, sec.section.value, sec.title, sec.text,
                 sec.word_count, sec.start_offset, sec.end_offset),
            )
            inserted += 1
        return inserted
    finally:
        cur.close()


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------
with DAG(
    dag_id="secsignal_ingest_filings",
    default_args=default_args,
    description="Ingest SEC EDGAR filings into Snowflake with text and image embeddings",
    schedule="0 6 * * 0",  # Sundays at 06:00 UTC
    start_date=datetime(2026, 3, 1),
    catchup=False,
    tags=["secsignal", "edgar", "ingestion"],
    params={
        "tickers": DEFAULT_TICKERS,
        "max_filings": MAX_FILINGS_PER_COMPANY,
    },
) as dag:

    t_fetch = PythonOperator(
        task_id="fetch_metadata",
        python_callable=fetch_metadata,
    )

    t_process = PythonOperator(
        task_id="process_filings",
        python_callable=process_filings,
    )

    t_images = PythonOperator(
        task_id="process_images",
        python_callable=process_images,
    )

    t_dbt = PythonOperator(
        task_id="run_dbt",
        python_callable=run_dbt,
    )

    t_embed = PythonOperator(
        task_id="embed_text",
        python_callable=embed_text,
    )

    t_embed_images = PythonOperator(
        task_id="embed_images",
        python_callable=embed_images,
    )

    # fetch → process filings → [process images, dbt] → [embed text, embed images]
    t_fetch >> t_process >> [t_images, t_dbt]
    t_dbt >> t_embed
    t_images >> t_embed_images
