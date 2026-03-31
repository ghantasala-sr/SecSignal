"""End-to-end test script for the SecSignal agent system.

Tests each tool individually against live Snowflake data, then runs
the full LangGraph pipeline with sample queries from PLAN.md.

Usage:
    cd /path/to/SecSignal
    source .env  # or use dotenv
    .venv/bin/python scripts/test_agents.py
"""

from __future__ import annotations

import json
import os
import sys
import time

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Load .env if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def separator(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def test_sql_tool() -> bool:
    """Test SQL tool queries against dbt marts."""
    separator("SQL Tool Tests")
    from secsignal.agents.tools.sql_tool import (
        query_financials,
        query_risk_factors,
        query_chart_data,
    )

    ok = True

    # Test financials
    print("1. query_financials(ticker='AAPL', limit=3)")
    rows = query_financials(ticker="AAPL", limit=3)
    print(f"   -> {len(rows)} rows")
    for r in rows:
        print(f"   {r.get('TICKER')} | {r.get('FILING_DATE')} | {r.get('SECTION_KEY')} | wc={r.get('WORD_COUNT')}")
    if not rows:
        print("   WARN: no financial rows for AAPL")
        ok = False

    # Test risk factors
    print("\n2. query_risk_factors(ticker='TSLA', limit=3)")
    rows = query_risk_factors(ticker="TSLA", limit=3)
    print(f"   -> {len(rows)} rows")
    for r in rows:
        print(f"   {r.get('TICKER')} | {r.get('FILING_DATE')} | wc={r.get('WORD_COUNT')} | delta={r.get('WORD_COUNT_DELTA')}")
    if not rows:
        print("   WARN: no risk factor rows for TSLA")

    # Test chart data
    print("\n3. query_chart_data(limit=3)")
    rows = query_chart_data(limit=3)
    print(f"   -> {len(rows)} rows")
    for r in rows:
        print(f"   {r.get('TICKER')} | {r.get('CHART_TYPE')} | {r.get('CHART_TITLE', '')[:50]}")

    return ok


def test_semantic_tool() -> bool:
    """Test Cortex Search retrieval."""
    separator("Semantic Tool Tests")
    from secsignal.agents.tools.semantic_tool import search_filing_text

    print("1. search_filing_text('revenue growth', ticker='AAPL', limit=2)")
    results = search_filing_text(query="revenue growth", ticker="AAPL", limit=2)
    print(f"   -> {len(results)} results")
    for r in results:
        print(f"   [{r.get('ticker')} | {r.get('filing_type')} | score={r.get('score', 0):.3f}]")
        print(f"   {r.get('content', '')[:120]}...")

    if not results:
        print("   FAIL: no search results")
        return False

    print("\n2. search_filing_text('risk factors', filing_type='10-K', limit=2)")
    results = search_filing_text(query="risk factors", filing_type="10-K", limit=2)
    print(f"   -> {len(results)} results")

    return True


def test_visual_tool() -> bool:
    """Test cross-modal chart search."""
    separator("Visual Tool Tests")
    from secsignal.agents.tools.visual_tool import search_charts

    print("1. search_charts('revenue breakdown chart', limit=2)")
    results = search_charts(query="revenue breakdown chart", limit=2)
    print(f"   -> {len(results)} results")
    for r in results:
        print(f"   [{r.get('TICKER')} | {r.get('CHART_TYPE')} | sim={r.get('SIMILARITY', 0):.3f}]")
        desc = r.get("DESCRIPTION", "")
        print(f"   {desc[:100] if desc else 'No description'}")
        b64 = r.get("IMAGE_DATA_B64", "")
        print(f"   image_data: {'yes' if b64 else 'no'} ({len(b64)} chars)")

    return True


def test_anomaly_scorer() -> bool:
    """Test z-score anomaly detection."""
    separator("Anomaly Scorer Tests")
    from secsignal.agents.tools.anomaly_scorer import detect_anomalies

    print("1. detect_anomalies(ticker=None) — scan all companies")
    anomalies = detect_anomalies(ticker=None)
    print(f"   -> {len(anomalies)} anomalies detected")
    for a in anomalies:
        print(
            f"   {a['ticker']} | {a['filing_date']} | "
            f"delta={a['value']:+,} | z={a['z_score']:+.2f} | {a['direction']}"
        )

    print("\n2. detect_anomalies(ticker='AAPL')")
    anomalies = detect_anomalies(ticker="AAPL")
    print(f"   -> {len(anomalies)} anomalies for AAPL")

    return True


def test_full_graph() -> None:
    """Run full LangGraph pipeline with sample queries."""
    separator("Full Graph — End-to-End Tests")
    from secsignal.agents.graph import run_query

    test_queries = [
        {
            "query": "How has Apple's risk factor disclosure changed over the last year?",
            "tickers": ["AAPL"],
            "expected_type": "trend",
        },
        {
            "query": "Compare AAPL and MSFT financial filing lengths",
            "tickers": ["AAPL", "MSFT"],
            "expected_type": "comparison",
        },
        {
            "query": "Are there any unusual changes in risk factor disclosures?",
            "tickers": [],
            "expected_type": "anomaly",
        },
    ]

    for i, tc in enumerate(test_queries, 1):
        print(f"\n--- Test {i}: {tc['query'][:60]}... ---")
        start = time.time()

        result = run_query(
            query=tc["query"],
            tickers=tc["tickers"] if tc["tickers"] else None,
        )

        elapsed = time.time() - start
        print(f"   Time: {elapsed:.1f}s")
        print(f"   Query type: {result.get('query_type', '?')} (expected: {tc['expected_type']})")
        print(f"   Tickers: {result.get('tickers', [])}")
        print(f"   Sources: {len(result.get('sources', []))}")
        print(f"   Charts: {len(result.get('retrieved_charts', []))}")
        print(f"   Anomalies: {len(result.get('anomaly_scores', []))}")
        print(f"   Answer ({len(result.get('final_answer', ''))} chars):")
        answer = result.get("final_answer", "")
        # Print first 400 chars of answer
        print(f"   {answer[:400]}{'...' if len(answer) > 400 else ''}")


def main() -> None:
    print("SecSignal Agent System — End-to-End Tests")
    print(f"Account: {os.environ.get('SNOWFLAKE_ACCOUNT', 'NOT SET')}")
    print(f"Database: {os.environ.get('SNOWFLAKE_DATABASE', 'NOT SET')}")
    print(f"LLM Model: {os.environ.get('CORTEX_LLM_MODEL', 'mistral-large2')}")

    # Run individual tool tests
    test_sql_tool()
    test_semantic_tool()
    test_visual_tool()
    test_anomaly_scorer()

    # Run full graph tests
    test_full_graph()

    separator("All Tests Complete")


if __name__ == "__main__":
    main()
