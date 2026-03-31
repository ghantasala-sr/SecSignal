"""Targeted extraction for remaining tickers (AAPL, NVDA, TSLA).

Processes one filing at a time with explicit flush and smaller text chunks.
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

LLM_MODEL = "mistral-large2"

EXTRACTION_PROMPT = """You are a financial data extraction engine. Extract all quantitative financial metrics from the following SEC filing MD&A text.

Return a JSON array of objects with: "metric_name", "metric_category" (one of: revenue, income, expense, margin, cash_flow, assets, growth, other), "value" (numeric, in millions), "period", "unit" (USD_millions, percent, ratio, count, other).

Rules: Extract ALL numeric data. Convert billions to millions. Return ONLY the JSON array, no markdown.

MD&A Text:
{text}"""


def run():
    conn = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database="SECSIGNAL",
        role=os.environ.get("SNOWFLAKE_ROLE", "TRAINING_ROLE"),
    )
    cursor = conn.cursor()

    # Check what we already have
    cursor.execute("""
        SELECT DISTINCT TICKER FROM SECSIGNAL.RAW.EXTRACTED_FINANCIALS
    """)
    existing = {row[0] for row in cursor.fetchall()}
    print(f"Already have data for: {existing}", flush=True)

    # Get filings for missing tickers
    cursor.execute("""
        SELECT f.FILING_ID, c.TICKER, f.FILING_TYPE, f.FILING_DATE,
               s.SECTION_KEY, s.SECTION_TEXT, s.WORD_COUNT
        FROM SECSIGNAL.RAW.RAW_FILING_SECTIONS s
        JOIN SECSIGNAL.RAW.RAW_FILINGS f ON s.FILING_ID = f.FILING_ID
        JOIN SECSIGNAL.RAW.RAW_COMPANIES c ON f.CIK = c.CIK
        WHERE ((s.SECTION_KEY = 'item_2' AND f.FILING_TYPE IN ('10-Q', '10-K'))
            OR (s.SECTION_KEY = 'item_7' AND f.FILING_TYPE = '10-K'))
          AND s.WORD_COUNT > 200
          AND c.TICKER NOT IN (SELECT DISTINCT TICKER FROM SECSIGNAL.RAW.EXTRACTED_FINANCIALS)
        ORDER BY s.WORD_COUNT ASC
    """)
    cols = [d[0] for d in cursor.description]
    filings = [dict(zip(cols, row)) for row in cursor.fetchall()]
    print(f"Filings to process: {len(filings)}", flush=True)

    for i, f in enumerate(filings, 1):
        ticker = f["TICKER"]
        ftype = f["FILING_TYPE"]
        fdate = f["FILING_DATE"]
        wc = f["WORD_COUNT"]
        text = f["SECTION_TEXT"]
        fid = f["FILING_ID"]

        # Truncate to 4000 words to avoid timeout
        words = text.split()
        if len(words) > 4000:
            text = " ".join(words[:4000])
            print(f"  Truncated {wc} -> 4000 words", flush=True)

        print(f"[{i}/{len(filings)}] {ticker} {ftype} ({fdate}) {wc}w ... ", end="", flush=True)

        prompt = EXTRACTION_PROMPT.format(text=text)
        try:
            cursor.execute(
                "SELECT SNOWFLAKE.CORTEX.COMPLETE(%s, %s) AS r",
                (LLM_MODEL, prompt),
            )
            raw = cursor.fetchone()[0]
        except Exception as e:
            print(f"LLM ERROR: {e}", flush=True)
            continue

        # Parse
        t = raw.strip()
        if t.startswith("```"):
            lines = t.split("\n")
            t = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        start, end = t.find("["), t.rfind("]")
        if start == -1 or end == -1:
            print("no JSON array found", flush=True)
            continue

        try:
            metrics = json.loads(t[start:end+1])
        except json.JSONDecodeError:
            print("JSON parse error", flush=True)
            continue

        inserted = 0
        for m in metrics:
            if not isinstance(m, dict):
                continue
            name = m.get("metric_name", "").strip()
            val = m.get("value")
            if not name or val is None:
                continue
            try:
                val = float(val)
            except (TypeError, ValueError):
                continue

            eid = hashlib.md5(f"{fid}:{name}:{m.get('period','')}".encode()).hexdigest()[:20]
            try:
                cursor.execute("""
                    INSERT INTO SECSIGNAL.RAW.EXTRACTED_FINANCIALS
                        (EXTRACT_ID, FILING_ID, TICKER, FILING_TYPE, FILING_DATE,
                         METRIC_NAME, METRIC_CATEGORY, VALUE, PERIOD, UNIT)
                    SELECT %s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                    WHERE NOT EXISTS (SELECT 1 FROM SECSIGNAL.RAW.EXTRACTED_FINANCIALS WHERE EXTRACT_ID=%s)
                """, (eid, fid, ticker, ftype, str(fdate), name,
                      m.get("metric_category","other"), val,
                      str(m.get("period","")), m.get("unit","other"), eid))
                inserted += 1
            except Exception as e:
                pass

        print(f"{inserted} metrics", flush=True)
        time.sleep(0.5)

    # Summary
    cursor.execute("""
        SELECT TICKER, COUNT(*) FROM SECSIGNAL.RAW.EXTRACTED_FINANCIALS
        GROUP BY TICKER ORDER BY TICKER
    """)
    print("\nFinal counts:", flush=True)
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]}", flush=True)

    cursor.close()
    conn.close()

if __name__ == "__main__":
    run()
