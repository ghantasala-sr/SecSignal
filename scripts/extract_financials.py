"""Extract structured financial metrics from MD&A text via Cortex COMPLETE.

Reads item_2 (10-Q) and item_7 (10-K) sections from RAW_FILING_SECTIONS,
sends each to mistral-large2 with a structured extraction prompt, parses
the JSON response, and inserts rows into RAW.EXTRACTED_FINANCIALS.

Usage:
    cd /Users/srinivasarithikghantasala/Downloads/SecSignal
    source .env
    python scripts/extract_financials.py
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()

import snowflake.connector

LLM_MODEL = os.environ.get("CORTEX_LLM_MODEL", "mistral-large2")

EXTRACTION_PROMPT = """You are a financial data extraction engine. Extract all quantitative financial metrics from the following SEC filing MD&A (Management's Discussion and Analysis) text.

Return a JSON array of objects, each with these fields:
- "metric_name": descriptive name (e.g. "Total Revenue", "Net Income", "Operating Margin")
- "metric_category": one of "revenue", "income", "expense", "margin", "cash_flow", "assets", "growth", "other"
- "value": numeric value (no commas, no dollar signs). Use millions as the base unit where applicable.
- "period": time period (e.g. "Q1 FY2025", "FY2024", "Three months ended December 2024")
- "unit": one of "USD_millions", "USD_billions", "percent", "ratio", "count", "other"

Rules:
1. Extract ALL numeric financial data points mentioned — revenue segments, costs, margins, YoY changes, etc.
2. If a value is in billions, convert to millions (multiply by 1000) and use "USD_millions".
3. If a value is a percentage (e.g. "grew 12%"), use "percent" as the unit.
4. Include year-over-year changes as separate metrics with category "growth".
5. Return ONLY the JSON array, no markdown fences or explanation.
6. If you cannot extract any metrics, return an empty array: []

MD&A Text:
{text}"""


def extract_financials() -> None:
    """Run the extraction pipeline."""
    conn = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ.get("SNOWFLAKE_DATABASE", "SECSIGNAL"),
        role=os.environ.get("SNOWFLAKE_ROLE", "TRAINING_ROLE"),
    )
    cursor = conn.cursor()

    try:
        # 1. Get all MD&A sections with reasonable content
        cursor.execute("""
            SELECT f.FILING_ID, c.TICKER, f.FILING_TYPE, f.FILING_DATE,
                   s.SECTION_KEY, s.SECTION_TEXT, s.WORD_COUNT
            FROM SECSIGNAL.RAW.RAW_FILING_SECTIONS s
            JOIN SECSIGNAL.RAW.RAW_FILINGS f ON s.FILING_ID = f.FILING_ID
            JOIN SECSIGNAL.RAW.RAW_COMPANIES c ON f.CIK = c.CIK
            WHERE ((s.SECTION_KEY = 'item_2' AND f.FILING_TYPE IN ('10-Q', '10-K'))
                OR (s.SECTION_KEY = 'item_7' AND f.FILING_TYPE = '10-K'))
              AND s.WORD_COUNT > 200
            ORDER BY c.TICKER, f.FILING_DATE DESC
        """)
        columns = [desc[0] for desc in cursor.description]
        filings = [dict(zip(columns, row)) for row in cursor.fetchall()]
        print(f"Found {len(filings)} MD&A sections to process")

        total_metrics = 0

        for i, filing in enumerate(filings, 1):
            filing_id = filing["FILING_ID"]
            ticker = filing["TICKER"]
            filing_type = filing["FILING_TYPE"]
            filing_date = filing["FILING_DATE"]
            content = filing["SECTION_TEXT"]
            word_count = filing["WORD_COUNT"]

            print(f"\n[{i}/{len(filings)}] {ticker} {filing_type} ({filing_date}) — {word_count} words")

            # Truncate very long texts to avoid token limits (~8k words max)
            words = content.split()
            if len(words) > 6000:
                content = " ".join(words[:6000])
                print(f"  Truncated to 6000 words")

            # 2. Call Cortex COMPLETE for extraction
            prompt = EXTRACTION_PROMPT.format(text=content)
            try:
                cursor.execute(
                    "SELECT SNOWFLAKE.CORTEX.COMPLETE(%s, %s) AS response",
                    (LLM_MODEL, prompt),
                )
                row = cursor.fetchone()
                raw_response = row[0] if row else "[]"
            except Exception as e:
                print(f"  ERROR calling Cortex COMPLETE: {e}")
                continue

            # 3. Parse JSON response
            metrics = _parse_extraction(raw_response)
            if not metrics:
                print(f"  No metrics extracted")
                continue

            print(f"  Extracted {len(metrics)} metrics")

            # 4. Insert into EXTRACTED_FINANCIALS
            inserted = 0
            for m in metrics:
                extract_id = hashlib.md5(
                    f"{filing_id}:{m['metric_name']}:{m.get('period', '')}".encode()
                ).hexdigest()[:20]

                try:
                    cursor.execute(
                        """
                        INSERT INTO SECSIGNAL.RAW.EXTRACTED_FINANCIALS
                            (EXTRACT_ID, FILING_ID, TICKER, FILING_TYPE, FILING_DATE,
                             METRIC_NAME, METRIC_CATEGORY, VALUE, PERIOD, UNIT)
                        SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        WHERE NOT EXISTS (
                            SELECT 1 FROM SECSIGNAL.RAW.EXTRACTED_FINANCIALS
                            WHERE EXTRACT_ID = %s
                        )
                        """,
                        (
                            extract_id, filing_id, ticker, filing_type,
                            str(filing_date), m["metric_name"],
                            m.get("metric_category", "other"),
                            m.get("value"), m.get("period", ""),
                            m.get("unit", "other"), extract_id,
                        ),
                    )
                    inserted += 1
                except Exception as e:
                    print(f"  Insert error for {m['metric_name']}: {e}")

            total_metrics += inserted
            print(f"  Inserted {inserted} rows")

            # Brief pause between LLM calls
            time.sleep(1)

        print(f"\n{'='*60}")
        print(f"Done. Total metrics extracted: {total_metrics}")

        # Verify
        cursor.execute("""
            SELECT TICKER, COUNT(*) as METRIC_COUNT
            FROM SECSIGNAL.RAW.EXTRACTED_FINANCIALS
            GROUP BY TICKER
            ORDER BY TICKER
        """)
        print("\nMetrics per ticker:")
        for row in cursor.fetchall():
            print(f"  {row[0]}: {row[1]}")

    finally:
        cursor.close()
        conn.close()


def _parse_extraction(raw: str) -> list[dict]:
    """Parse LLM extraction response into a list of metric dicts."""
    text = raw.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        text = text.strip()

    # Try to find JSON array in the response
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        return []

    try:
        metrics = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        print(f"  JSON parse error, raw: {text[:200]}...")
        return []

    if not isinstance(metrics, list):
        return []

    # Validate and normalize
    valid = []
    for m in metrics:
        if not isinstance(m, dict):
            continue
        name = m.get("metric_name", "").strip()
        value = m.get("value")
        if not name or value is None:
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        valid.append({
            "metric_name": name,
            "metric_category": m.get("metric_category", "other"),
            "value": value,
            "period": str(m.get("period", "")),
            "unit": m.get("unit", "other"),
        })

    return valid


if __name__ == "__main__":
    extract_financials()
