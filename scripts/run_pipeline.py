"""SecSignal ingestion pipeline — fetches EDGAR filings, uploads to GCS,
parses HTML into sections, runs dbt quality checks, and embeds text chunks.

Usage:
    python scripts/run_pipeline.py --tickers AAPL MSFT --max-filings 3
    python scripts/run_pipeline.py --skip-embeddings
    python scripts/run_pipeline.py --skip-dbt
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import os
import subprocess
import sys
import uuid
from pathlib import Path

import snowflake.connector
import structlog
from dotenv import load_dotenv

# Ensure the project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from secsignal.ingestion.edgar_client import EdgarClient, Filing
from secsignal.ingestion.filing_parser import FilingParser, chunk_text
from secsignal.ingestion.gcs_uploader import GCSUploader
from secsignal.embeddings.cortex_embed import CortexEmbedder
from secsignal.processing.document_parser import DocumentParser
from secsignal.processing.image_extractor import ImageExtractor
from secsignal.processing.chart_analyzer import ChartAnalyzer

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.PrintLoggerFactory(),
)
log = structlog.get_logger("pipeline")

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]
DEFAULT_MAX_FILINGS = 5
FILING_TYPES = ("10-K", "10-Q", "8-K")
CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200


# ---------------------------------------------------------------------------
# Snowflake helpers
# ---------------------------------------------------------------------------
def get_snowflake_connection() -> snowflake.connector.SnowflakeConnection:
    """Create a Snowflake connection from environment variables."""
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        role=os.environ["SNOWFLAKE_ROLE"],
    )


def upsert_company(conn, cik: str, ticker: str, company_name: str) -> None:
    """Insert or update a company record in RAW_COMPANIES."""
    cur = conn.cursor()
    try:
        cur.execute(
            """
            MERGE INTO SECSIGNAL.RAW.RAW_COMPANIES tgt
            USING (SELECT %s AS CIK, %s AS TICKER, %s AS COMPANY_NAME) src
            ON tgt.CIK = src.CIK
            WHEN MATCHED THEN UPDATE SET
                TICKER = src.TICKER,
                COMPANY_NAME = src.COMPANY_NAME,
                LOADED_AT = CURRENT_TIMESTAMP()
            WHEN NOT MATCHED THEN INSERT (CIK, TICKER, COMPANY_NAME)
                VALUES (src.CIK, src.TICKER, src.COMPANY_NAME)
            """,
            (cik, ticker, company_name),
        )
    finally:
        cur.close()


def upsert_filing(conn, filing: Filing, gcs_uri: str | None, file_size: int | None) -> None:
    """Insert or update a filing record in RAW_FILINGS."""
    cur = conn.cursor()
    try:
        cur.execute(
            """
            MERGE INTO SECSIGNAL.RAW.RAW_FILINGS tgt
            USING (SELECT %s AS FILING_ID) src
            ON tgt.FILING_ID = src.FILING_ID
            WHEN NOT MATCHED THEN INSERT
                (FILING_ID, CIK, TICKER, FILING_TYPE, FILING_DATE,
                 PRIMARY_DOCUMENT, DOCUMENT_URL, GCS_URI, FILE_SIZE_BYTES)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                filing.accession_number,
                filing.accession_number,
                filing.cik,
                filing.ticker,
                filing.filing_type,
                filing.filing_date,
                filing.primary_document,
                filing.primary_doc_url,
                gcs_uri,
                file_size,
            ),
        )
    finally:
        cur.close()


def insert_sections(conn, filing_id: str, sections) -> int:
    """Insert parsed sections into RAW_FILING_SECTIONS. Returns rows inserted."""
    cur = conn.cursor()
    inserted = 0
    try:
        seen_keys: dict[str, int] = {}
        for sec in sections:
            # Disambiguate when multiple sections share the same enum
            # (e.g. items 10, 11, 12 all map to "other")
            key = sec.section.value
            seen_keys[key] = seen_keys.get(key, 0) + 1
            if seen_keys[key] > 1:
                section_id = f"{filing_id}_{key}_{seen_keys[key]}"
            else:
                section_id = f"{filing_id}_{key}"
            # Skip if already exists
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
        return inserted
    finally:
        cur.close()


def put_to_internal_stage(
    conn, html_bytes: bytes, filing_id: str, filename: str
) -> str:
    """PUT an HTML filing to the internal FILING_DOCUMENTS_STAGE.

    AI_PARSE_DOCUMENT requires files on a Snowflake internal stage.
    Returns the stage path suitable for parse_from_stage().
    """
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".htm", delete=False) as tmp:
        tmp.write(html_bytes)
        tmp_path = tmp.name

    stage_dir = filing_id.replace("-", "_")
    cur = conn.cursor()
    try:
        cur.execute(
            f"PUT 'file://{tmp_path}' @SECSIGNAL.RAW.FILING_DOCUMENTS_STAGE/{stage_dir}/ "
            "AUTO_COMPRESS=FALSE OVERWRITE=TRUE"
        )
        log.info("put_to_stage", filing_id=filing_id, stage_dir=stage_dir)
    finally:
        cur.close()
        os.unlink(tmp_path)

    return f"@SECSIGNAL.RAW.FILING_DOCUMENTS_STAGE/{stage_dir}/{os.path.basename(tmp_path)}"


def run_image_pipeline(
    conn,
    html_bytes: bytes,
    filing_id: str,
    filename: str,
    filing_metadata: dict,
    embedder: CortexEmbedder | None,
    document_url: str = "",
) -> dict[str, int]:
    """Run the image extraction pipeline for a single filing.

    For HTML filings: parse <img> tags → download from EDGAR → store → analyze.
    For PDF filings: PUT to stage → AI_PARSE_DOCUMENT → extract → analyze.

    Returns dict with image/chart/embed counts.
    """
    counts = {"images": 0, "chart_extracts": 0, "image_embeddings": 0}

    try:
        extractor = ImageExtractor(conn)

        # HTML filings: extract images by parsing <img> tags and downloading
        user_agent = os.environ.get("EDGAR_USER_AGENT", "SecSignal agent@secsignal.dev")
        images = extractor.extract_images_from_html(
            html_bytes, filing_id, document_url, user_agent
        )

        if not images:
            log.info("no_images_found", filing_id=filing_id)
            return counts

        # Store images in FILING_IMAGES
        stored = extractor.store_images(images)
        counts["images"] = stored
        log.info("images_stored", filing_id=filing_id, count=stored)

        # Analyze charts with AI_EXTRACT
        analyzer = ChartAnalyzer(conn)
        extracts = analyzer.analyze_batch(images)
        if extracts:
            stored = analyzer.store_extracts(extracts)
            counts["chart_extracts"] = stored
            log.info("chart_extracts_stored", filing_id=filing_id, count=stored)

        # Embed images (if embedder provided)
        if embedder and images:
            descriptions = {
                ext.image_id: f"{ext.chart_title} ({ext.chart_type})"
                for ext in extracts
            }
            for img in images:
                if img.image_id not in descriptions:
                    descriptions[img.image_id] = f"Filing image from page {img.page_number}"

            embed_count = embedder.embed_filing_images(
                images, descriptions, filing_metadata
            )
            counts["image_embeddings"] = embed_count
            log.info("images_embedded", filing_id=filing_id, count=embed_count)

    except Exception:
        log.exception("image_pipeline_failed", filing_id=filing_id)

    return counts


# ---------------------------------------------------------------------------
# dbt integration
# ---------------------------------------------------------------------------
def run_dbt_build() -> bool:
    """Run dbt build to refresh staging → intermediate → marts with tests.

    Returns True if successful, False otherwise.
    """
    dbt_dir = PROJECT_ROOT / "dbt"
    dbt_bin = PROJECT_ROOT / ".venv" / "bin" / "dbt"

    if not dbt_bin.exists():
        log.warning("dbt_not_found", path=str(dbt_bin))
        return False

    log.info("running_dbt_build", dbt_dir=str(dbt_dir))
    env = {**os.environ, "SF_SKIP_TOKEN_FILE_PERMISSIONS_VERIFICATION": "true"}
    result = subprocess.run(
        [str(dbt_bin), "build", "--profiles-dir", "."],
        cwd=str(dbt_dir),
        capture_output=True,
        text=True,
        env=env,
    )

    if result.returncode != 0:
        log.error("dbt_build_failed", stderr=result.stderr[-500:] if result.stderr else "")
        return False

    # Extract summary line
    for line in result.stdout.splitlines():
        if "PASS=" in line or "Completed" in line:
            log.info("dbt_build_result", summary=line.strip())

    return True


def fetch_validated_sections(conn, filing_ids: list[str]) -> list[dict]:
    """Read validated sections from INTERMEDIATE.INT_PARSED_SECTIONS.

    Only returns sections that passed dbt data quality checks.
    """
    if not filing_ids:
        return []

    placeholders = ", ".join(["%s"] * len(filing_ids))
    cur = conn.cursor()
    try:
        cur.execute(
            f"""
            SELECT
                SECTION_ID, FILING_ID, TICKER, FILING_TYPE, FILING_DATE,
                SECTION_KEY, SECTION_TEXT, WORD_COUNT
            FROM SECSIGNAL.INTERMEDIATE.INT_PARSED_SECTIONS
            WHERE FILING_ID IN ({placeholders})
            ORDER BY FILING_ID, SECTION_KEY
            """,
            filing_ids,
        )
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]
    finally:
        cur.close()


# ---------------------------------------------------------------------------
# Async EDGAR fetch
# ---------------------------------------------------------------------------
async def fetch_company_filings(
    tickers: list[str],
    max_filings: int,
    user_agent: str,
) -> dict[str, list[Filing]]:
    """Resolve tickers and fetch filing metadata from EDGAR."""
    results: dict[str, list[Filing]] = {}

    async with EdgarClient(user_agent=user_agent) as client:
        for ticker in tickers:
            log.info("resolving_ticker", ticker=ticker)
            cik = await client.get_cik_for_ticker(ticker)
            if not cik:
                log.warning("ticker_not_found", ticker=ticker)
                continue

            log.info("fetching_filings", ticker=ticker, cik=cik)
            filings = await client.get_company_filings(
                cik=cik,
                filing_types=FILING_TYPES,
                max_filings=max_filings,
            )
            results[ticker] = filings
            log.info("fetched", ticker=ticker, count=len(filings))

    return results


async def download_filing_html(filing: Filing, user_agent: str) -> bytes:
    """Download the primary document for a filing."""
    async with EdgarClient(user_agent=user_agent) as client:
        return await client.download_filing_document(filing.primary_doc_url)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def run_pipeline(
    tickers: list[str],
    max_filings: int,
    skip_embeddings: bool,
    skip_dbt: bool = False,
) -> dict[str, int]:
    """Execute the full ingestion pipeline.

    Returns a summary dict with counts.
    """
    load_dotenv(PROJECT_ROOT / ".env")

    user_agent = os.environ.get("EDGAR_USER_AGENT", "SecSignal agent@secsignal.dev")
    gcs_bucket = os.environ.get("GCS_BUCKET", "secsignal-raw")

    # ---------- 1. Fetch metadata from EDGAR ----------
    log.info("step_1_fetch_metadata", tickers=tickers, max_filings=max_filings)
    ticker_filings = asyncio.run(fetch_company_filings(tickers, max_filings, user_agent))

    total_filings = sum(len(f) for f in ticker_filings.values())
    log.info("metadata_fetched", companies=len(ticker_filings), filings=total_filings)

    if total_filings == 0:
        log.warning("no_filings_found")
        return {"companies": 0, "filings": 0, "sections": 0, "embeddings": 0}

    # ---------- 2. Connect to Snowflake ----------
    log.info("step_2_connect_snowflake")
    conn = get_snowflake_connection()

    # ---------- 3. Initialize modules ----------
    uploader = GCSUploader(bucket_name=gcs_bucket)
    parser = FilingParser()

    stats = {"companies": 0, "filings": 0, "sections": 0, "embeddings": 0, "images": 0, "chart_extracts": 0}
    processed_filing_ids: list[str] = []

    try:
        for ticker, filings in ticker_filings.items():
            if not filings:
                continue

            # Insert company
            sample = filings[0]
            upsert_company(conn, sample.cik, sample.ticker, sample.company_name)
            stats["companies"] += 1
            log.info("company_stored", ticker=ticker, cik=sample.cik)

            for filing in filings:
                filing_id = filing.accession_number
                log.info(
                    "processing_filing",
                    ticker=ticker,
                    type=filing.filing_type,
                    date=filing.filing_date,
                    accession=filing_id,
                )

                try:
                    # --- Download HTML ---
                    log.info("downloading_html", url=filing.primary_doc_url)
                    html_bytes = asyncio.run(download_filing_html(filing, user_agent))
                    file_size = len(html_bytes)
                    log.info("downloaded", size_kb=round(file_size / 1024, 1))

                    # --- Upload to GCS ---
                    log.info("uploading_to_gcs")
                    gcs_uri = uploader.upload_filing(
                        data=html_bytes,
                        ticker=ticker,
                        filing_type=filing.filing_type,
                        filing_date=filing.filing_date,
                        accession_number=filing_id,
                        filename=filing.primary_document,
                    )
                    log.info("uploaded", gcs_uri=gcs_uri)

                    # --- Store filing metadata ---
                    upsert_filing(conn, filing, gcs_uri, file_size)
                    stats["filings"] += 1

                    # --- Parse HTML into sections ---
                    log.info("parsing_html")
                    parsed = parser.parse_html(html_bytes, filing_id, filing.filing_type)
                    log.info(
                        "parsed",
                        sections=len(parsed.sections),
                        tables=len(parsed.tables),
                    )

                    # --- Store sections in RAW ---
                    sec_count = insert_sections(conn, filing_id, parsed.sections)
                    stats["sections"] += sec_count
                    log.info("sections_stored", count=sec_count)

                    # --- Image pipeline: parse <img> tags → download → analyze ---
                    log.info("running_image_pipeline", filing_id=filing_id)
                    img_counts = run_image_pipeline(
                        conn=conn,
                        html_bytes=html_bytes,
                        filing_id=filing_id,
                        filename=filing.primary_document,
                        filing_metadata={
                            "ticker": ticker,
                            "filing_type": filing.filing_type,
                            "filing_date": filing.filing_date,
                        },
                        embedder=None,  # Image embedding happens after dbt, below
                        document_url=filing.primary_doc_url,
                    )
                    stats["images"] += img_counts["images"]
                    stats["chart_extracts"] += img_counts["chart_extracts"]
                    log.info("image_pipeline_done", **img_counts)

                    processed_filing_ids.append(filing_id)

                except Exception:
                    log.exception("filing_failed", filing_id=filing_id)
                    continue

        # ---------- 4. Run dbt build ----------
        if not skip_dbt and processed_filing_ids:
            log.info("step_4_dbt_build")
            dbt_ok = run_dbt_build()
            if not dbt_ok:
                log.warning("dbt_build_failed_skipping_validated_embed")
        elif skip_dbt:
            log.info("step_4_dbt_skipped")

        # ---------- 5. Embed validated sections ----------
        if not skip_embeddings and processed_filing_ids:
            embedder = CortexEmbedder(conn)

            if not skip_dbt:
                # Read from dbt-validated intermediate table
                log.info("step_5_embed_from_intermediate", filing_count=len(processed_filing_ids))
                validated = fetch_validated_sections(conn, processed_filing_ids)
                log.info("validated_sections_fetched", count=len(validated))

                chunks = []
                for sec in validated:
                    if sec["WORD_COUNT"] < 20:
                        continue
                    text_chunks = chunk_text(sec["SECTION_TEXT"], CHUNK_SIZE, CHUNK_OVERLAP)
                    for idx, chunk_text_str in enumerate(text_chunks):
                        chunks.append({
                            "text": chunk_text_str,
                            "filing_id": sec["FILING_ID"],
                            "section_key": sec["SECTION_KEY"],
                            "chunk_index": idx,
                            "ticker": sec["TICKER"],
                            "filing_type": sec["FILING_TYPE"],
                            "filing_date": sec["FILING_DATE"],
                        })
            else:
                # Fallback: embed from RAW sections directly (no dbt validation)
                log.info("step_5_embed_from_raw", filing_count=len(processed_filing_ids))
                placeholders = ", ".join(["%s"] * len(processed_filing_ids))
                cur = conn.cursor()
                try:
                    cur.execute(
                        f"""
                        SELECT s.SECTION_ID, s.FILING_ID, f.TICKER, f.FILING_TYPE,
                               f.FILING_DATE, s.SECTION_KEY, s.SECTION_TEXT, s.WORD_COUNT
                        FROM SECSIGNAL.RAW.RAW_FILING_SECTIONS s
                        JOIN SECSIGNAL.RAW.RAW_FILINGS f ON s.FILING_ID = f.FILING_ID
                        WHERE s.FILING_ID IN ({placeholders})
                        """,
                        processed_filing_ids,
                    )
                    columns = [desc[0] for desc in cur.description]
                    raw_sections = [dict(zip(columns, row)) for row in cur.fetchall()]
                finally:
                    cur.close()

                chunks = []
                for sec in raw_sections:
                    if sec["WORD_COUNT"] < 20:
                        continue
                    text_chunks = chunk_text(sec["SECTION_TEXT"], CHUNK_SIZE, CHUNK_OVERLAP)
                    for idx, chunk_text_str in enumerate(text_chunks):
                        chunks.append({
                            "text": chunk_text_str,
                            "filing_id": sec["FILING_ID"],
                            "section_key": sec["SECTION_KEY"],
                            "chunk_index": idx,
                            "ticker": sec["TICKER"],
                            "filing_type": sec["FILING_TYPE"],
                            "filing_date": sec["FILING_DATE"],
                        })

            if chunks:
                embed_count = embedder.embed_filing_text(chunks)
                stats["embeddings"] += embed_count
                log.info("embedded", chunks=embed_count)
            else:
                log.info("no_chunks_to_embed")

            # ---------- 6. Embed images (voyage-multimodal-3) ----------
            log.info("step_6_embed_images")
            cur = conn.cursor()
            try:
                cur.execute(
                    "SELECT IMAGE_ID, FILING_ID FROM SECSIGNAL.RAW.FILING_IMAGES"
                )
                image_rows = cur.fetchall()
            finally:
                cur.close()

            if image_rows:
                # Fetch full image + chart data for embedding
                from secsignal.processing.image_extractor import ExtractedImage

                cur = conn.cursor()
                try:
                    cur.execute(
                        """
                        SELECT fi.IMAGE_ID, fi.FILING_ID, fi.IMAGE_INDEX,
                               fi.IMAGE_DATA_B64, fi.IMAGE_FORMAT, fi.PAGE_NUMBER,
                               fi.BOUNDING_BOX,
                               f.TICKER, f.FILING_TYPE, f.FILING_DATE,
                               ce.CHART_TITLE, ce.CHART_TYPE
                        FROM SECSIGNAL.RAW.FILING_IMAGES fi
                        JOIN SECSIGNAL.RAW.RAW_FILINGS f ON fi.FILING_ID = f.FILING_ID
                        LEFT JOIN SECSIGNAL.RAW.CHART_EXTRACTS ce ON fi.IMAGE_ID = ce.IMAGE_ID
                        """
                    )
                    rows = cur.fetchall()
                    columns = [desc[0] for desc in cur.description]
                    image_data = [dict(zip(columns, row)) for row in rows]
                finally:
                    cur.close()

                # Group by filing for embed_filing_images
                from collections import defaultdict
                by_filing: dict[str, list] = defaultdict(list)
                for row in image_data:
                    by_filing[row["FILING_ID"]].append(row)

                for fid, rows in by_filing.items():
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
                        for r in rows
                    ]
                    descriptions = {}
                    metadata = {
                        "ticker": rows[0]["TICKER"],
                        "filing_type": rows[0]["FILING_TYPE"],
                        "filing_date": rows[0]["FILING_DATE"],
                    }
                    for r in rows:
                        title = r.get("CHART_TITLE") or f"Filing image from page {r['PAGE_NUMBER']}"
                        ctype = r.get("CHART_TYPE") or "image"
                        descriptions[r["IMAGE_ID"]] = f"{title} ({ctype})"

                    count = embedder.embed_filing_images(images, descriptions, metadata)
                    stats["embeddings"] += count
                    log.info("images_embedded", filing_id=fid, count=count)
            else:
                log.info("no_images_to_embed")

    finally:
        conn.close()
        log.info("snowflake_connection_closed")

    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="SecSignal EDGAR ingestion pipeline")
    parser.add_argument(
        "--tickers",
        nargs="+",
        default=DEFAULT_TICKERS,
        help=f"Tickers to ingest (default: {DEFAULT_TICKERS})",
    )
    parser.add_argument(
        "--max-filings",
        type=int,
        default=DEFAULT_MAX_FILINGS,
        help=f"Max filings per company (default: {DEFAULT_MAX_FILINGS})",
    )
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Skip embedding step (useful for testing ingestion only)",
    )
    parser.add_argument(
        "--skip-dbt",
        action="store_true",
        help="Skip dbt build (embed directly from RAW sections)",
    )
    args = parser.parse_args()

    log.info(
        "pipeline_start",
        tickers=args.tickers,
        max_filings=args.max_filings,
        skip_embeddings=args.skip_embeddings,
        skip_dbt=args.skip_dbt,
    )

    stats = run_pipeline(
        tickers=args.tickers,
        max_filings=args.max_filings,
        skip_embeddings=args.skip_embeddings,
        skip_dbt=args.skip_dbt,
    )

    log.info("pipeline_complete", **stats)
    print("\n" + "=" * 60)
    print("  SecSignal Pipeline Summary")
    print("=" * 60)
    print(f"  Companies ingested : {stats['companies']}")
    print(f"  Filings processed  : {stats['filings']}")
    print(f"  Sections stored    : {stats['sections']}")
    print(f"  Images extracted   : {stats['images']}")
    print(f"  Chart extracts     : {stats['chart_extracts']}")
    print(f"  Chunks embedded    : {stats['embeddings']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
