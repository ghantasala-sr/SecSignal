"""Evaluation runner — executes test cases, scores them, persists results.

Runs each test case through the agent graph (non-streaming), applies all
scorers, and persists results to SECSIGNAL.EVALUATION tables in Snowflake.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog

from secsignal.agents.connection import get_snowflake_connection
from secsignal.agents.graph import agent_graph
from secsignal.agents.state import FilingState
from secsignal.evaluation.scorers import score_all
from secsignal.evaluation.test_cases import TestCase, get_test_cases

logger = structlog.get_logger(__name__)


def _run_single_case(test_case: TestCase) -> dict[str, Any]:
    """Run a single test case through the agent graph and return full state.

    Uses agent_graph.invoke directly (not run_query) to capture the full
    state including retrieved_chunks, sql_results, and web_context that
    the faithfulness scorer needs.
    """
    initial_state: FilingState = {
        "query": test_case.query,
        "query_type": "general",
        "tickers": [],
        "time_range": "all",
        "visual_intent": False,
        "execution_plan": [],
        "unknown_tickers": [],
        "retrieved_chunks": [],
        "retrieved_charts": [],
        "sql_results": [],
        "anomaly_scores": [],
        "generated_charts": [],
        "web_context": "",
        "web_sources": [],
        "conversation_history": test_case.context or [],
        "final_answer": "",
        "sources": [],
    }

    start = time.time()
    result = agent_graph.invoke(initial_state)
    latency_ms = int((time.time() - start) * 1000)

    return {
        "query": test_case.query,
        "query_type": result.get("query_type", "general"),
        "tickers": result.get("tickers", []),
        "execution_plan": result.get("execution_plan", []),
        "final_answer": result.get("final_answer", ""),
        "sources": result.get("sources", []),
        "retrieved_chunks": result.get("retrieved_chunks", []),
        "retrieved_charts": result.get("retrieved_charts", []),
        "sql_results": result.get("sql_results", []),
        "anomaly_scores": result.get("anomaly_scores", []),
        "generated_charts": result.get("generated_charts", []),
        "web_context": result.get("web_context", ""),
        "web_sources": result.get("web_sources", []),
        "latency_ms": latency_ms,
    }


def _persist_run(run_id: str, started_at: datetime, results: list[dict[str, Any]]) -> None:
    """Persist evaluation run summary to EVAL_RUNS."""
    if not results:
        return

    conn = get_snowflake_connection()
    cursor = conn.cursor()

    avg_routing = sum(r["scores"]["routing"]["score"] for r in results) / len(results)
    avg_retrieval = sum(r["scores"]["retrieval"]["score"] for r in results) / len(results)
    avg_answer = sum(r["scores"]["answer_quality"]["score"] for r in results) / len(results)
    avg_faith = sum(r["scores"]["faithfulness"]["score"] for r in results) / len(results)
    avg_overall = sum(r["scores"]["overall_score"] for r in results) / len(results)
    total_latency = sum(r["latency_ms"] for r in results)

    try:
        cursor.execute(
            """INSERT INTO SECSIGNAL.EVALUATION.EVAL_RUNS
               (RUN_ID, STARTED_AT, COMPLETED_AT, MODEL, TEST_CASE_COUNT,
                AVG_ROUTING_SCORE, AVG_RETRIEVAL_SCORE, AVG_ANSWER_SCORE,
                AVG_FAITHFULNESS_SCORE, AVG_OVERALL_SCORE, TOTAL_LATENCY_MS)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                run_id,
                started_at.isoformat(),
                datetime.now(timezone.utc).isoformat(),
                "claude-sonnet-4-6",
                len(results),
                round(avg_routing, 2),
                round(avg_retrieval, 2),
                round(avg_answer, 2),
                round(avg_faith, 2),
                round(avg_overall, 2),
                total_latency,
            ),
        )
    finally:
        cursor.close()


def _persist_result(run_id: str, test_case: TestCase, result: dict[str, Any], scores: dict[str, Any], latency_ms: int) -> None:
    """Persist a single test case result to EVAL_RESULTS."""
    conn = get_snowflake_connection()
    cursor = conn.cursor()

    result_id = str(uuid.uuid4())
    answer = result.get("final_answer", "")

    # Build raw output (truncated to avoid VARIANT size limits)
    raw_output = {
        "query_type": result.get("query_type"),
        "tickers": result.get("tickers", []),
        "source_count": len(result.get("sources", [])),
        "chunk_count": len(result.get("retrieved_chunks", [])),
        "answer_preview": answer[:500],
    }

    # Scorer details
    scorer_details = {
        "routing": scores["routing"],
        "retrieval": scores["retrieval"],
        "answer_quality": scores["answer_quality"],
        "faithfulness": scores["faithfulness"],
    }

    try:
        cursor.execute(
            """INSERT INTO SECSIGNAL.EVALUATION.EVAL_RESULTS
               (RESULT_ID, RUN_ID, TEST_CASE_ID, ACTUAL_QUERY_TYPE, ACTUAL_TICKERS,
                ROUTING_SCORE, RETRIEVAL_SCORE, ANSWER_SCORE, FAITHFULNESS_SCORE,
                OVERALL_SCORE, LATENCY_MS, RETRIEVED_CHUNK_COUNT, SOURCE_COUNT,
                ANSWER_LENGTH, ANSWER_PREVIEW, RAW_OUTPUT, SCORER_DETAILS)
               VALUES (%s, %s, %s, %s, PARSE_JSON(%s), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, PARSE_JSON(%s), PARSE_JSON(%s))""",
            (
                result_id,
                run_id,
                test_case.id,
                result.get("query_type", "general"),
                json.dumps(result.get("tickers", [])),
                scores["routing"]["score"],
                scores["retrieval"]["score"],
                scores["answer_quality"]["score"],
                scores["faithfulness"]["score"],
                scores["overall_score"],
                latency_ms,
                len(result.get("retrieved_chunks", [])),
                len(result.get("sources", [])),
                len(answer),
                answer[:200],
                json.dumps(raw_output),
                json.dumps(scorer_details, default=str),
            ),
        )
    finally:
        cursor.close()


def run_evaluation(
    category: str | None = None,
    persist: bool = True,
    verbose: bool = True,
) -> dict[str, Any]:
    """Run the full evaluation suite.

    Args:
        category: Optional filter — 'trend', 'comparison', 'anomaly', 'followup'.
        persist: Whether to save results to Snowflake.
        verbose: Whether to print progress to stdout.

    Returns:
        Dict with run_id, per-case results, and aggregate scores.
    """
    test_cases = get_test_cases(category)
    if not test_cases:
        print(f"No test cases found for category: {category}")
        return {"error": "No test cases found"}

    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)
    all_results: list[dict[str, Any]] = []

    if verbose:
        print(f"\n{'='*70}")
        print(f"  SecSignal Evaluation Run: {run_id[:8]}...")
        print(f"  Test cases: {len(test_cases)} | Category: {category or 'all'}")
        print(f"{'='*70}\n")

    for i, tc in enumerate(test_cases, 1):
        if verbose:
            print(f"  [{i}/{len(test_cases)}] {tc.id}: {tc.query[:60]}...")

        try:
            # Run through agent graph
            result = _run_single_case(tc)
            latency_ms = result["latency_ms"]

            if verbose:
                print(f"           → {result['query_type']} | {result['tickers']} | {latency_ms}ms")

            # Score
            scores = score_all(tc, result)

            if verbose:
                print(
                    f"           → routing={scores['routing']['score']:.1f}  "
                    f"retrieval={scores['retrieval']['score']:.1f}  "
                    f"answer={scores['answer_quality']['score']:.1f}  "
                    f"faithful={scores['faithfulness']['score']:.1f}  "
                    f"overall={scores['overall_score']:.1f}"
                )

            case_result = {
                "test_case_id": tc.id,
                "category": tc.category,
                "query": tc.query,
                "scores": scores,
                "latency_ms": latency_ms,
                "query_type": result["query_type"],
                "tickers": result.get("tickers", []),
            }
            all_results.append(case_result)

            # Persist individual result
            if persist:
                _persist_result(run_id, tc, result, scores, latency_ms)

        except Exception as exc:
            logger.exception("eval_case_failed", test_case_id=tc.id)
            if verbose:
                print(f"           → ERROR: {exc}")
            all_results.append({
                "test_case_id": tc.id,
                "category": tc.category,
                "query": tc.query,
                "scores": {
                    "routing": {"score": 1.0},
                    "retrieval": {"score": 1.0},
                    "answer_quality": {"score": 1.0},
                    "faithfulness": {"score": 1.0},
                    "overall_score": 1.0,
                },
                "latency_ms": 0,
                "error": str(exc),
            })

    # Aggregate scores
    n = len(all_results)
    agg = {
        "run_id": run_id,
        "test_case_count": n,
        "category": category or "all",
        "avg_routing": round(sum(r["scores"]["routing"]["score"] for r in all_results) / n, 2) if n else 0,
        "avg_retrieval": round(sum(r["scores"]["retrieval"]["score"] for r in all_results) / n, 2) if n else 0,
        "avg_answer": round(sum(r["scores"]["answer_quality"]["score"] for r in all_results) / n, 2) if n else 0,
        "avg_faithfulness": round(sum(r["scores"]["faithfulness"]["score"] for r in all_results) / n, 2) if n else 0,
        "avg_overall": round(sum(r["scores"]["overall_score"] for r in all_results) / n, 2) if n else 0,
        "total_latency_ms": sum(r["latency_ms"] for r in all_results),
        "results": all_results,
    }

    # Persist run summary
    if persist and all_results:
        _persist_run(run_id, started_at, all_results)

    if verbose:
        _print_summary(agg)

    return agg


def _print_summary(agg: dict[str, Any]) -> None:
    """Print a human-readable evaluation summary."""
    print(f"\n{'='*70}")
    print(f"  EVALUATION SUMMARY — Run {agg['run_id'][:8]}...")
    print(f"{'='*70}")
    print(f"  Category:     {agg['category']}")
    print(f"  Test cases:   {agg['test_case_count']}")
    print(f"  Total time:   {agg['total_latency_ms'] / 1000:.1f}s")
    print()
    print(f"  {'Dimension':<20} {'Avg Score':>10}  {'Rating':>10}")
    print(f"  {'-'*20} {'-'*10}  {'-'*10}")

    for name, key in [
        ("Routing", "avg_routing"),
        ("Retrieval", "avg_retrieval"),
        ("Answer Quality", "avg_answer"),
        ("Faithfulness", "avg_faithfulness"),
        ("OVERALL", "avg_overall"),
    ]:
        score = agg[key]
        rating = _score_to_rating(score)
        marker = " <--" if name == "OVERALL" else ""
        print(f"  {name:<20} {score:>10.2f}  {rating:>10}{marker}")

    print()

    # Per-category breakdown if running all
    categories = {}
    for r in agg["results"]:
        cat = r.get("category", "unknown")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(r["scores"]["overall_score"])

    if len(categories) > 1:
        print(f"  {'Category':<20} {'Cases':>6} {'Avg Overall':>12}")
        print(f"  {'-'*20} {'-'*6} {'-'*12}")
        for cat, scores in sorted(categories.items()):
            avg = sum(scores) / len(scores)
            print(f"  {cat:<20} {len(scores):>6} {avg:>12.2f}")
        print()

    # Worst performing cases
    results_sorted = sorted(agg["results"], key=lambda r: r["scores"]["overall_score"])
    if results_sorted:
        print("  Lowest scoring cases:")
        for r in results_sorted[:3]:
            print(f"    - {r['test_case_id']}: {r['scores']['overall_score']:.2f} — {r['query'][:50]}...")
        print()

    print(f"{'='*70}\n")


def _score_to_rating(score: float) -> str:
    """Convert a 1-5 score to a human-readable rating."""
    if score >= 4.5:
        return "Excellent"
    elif score >= 3.5:
        return "Good"
    elif score >= 2.5:
        return "Fair"
    elif score >= 1.5:
        return "Poor"
    else:
        return "Failing"


def compare_runs() -> None:
    """Compare the last two evaluation runs from Snowflake."""
    conn = get_snowflake_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT RUN_ID, STARTED_AT, TEST_CASE_COUNT,
                   AVG_ROUTING_SCORE, AVG_RETRIEVAL_SCORE,
                   AVG_ANSWER_SCORE, AVG_FAITHFULNESS_SCORE,
                   AVG_OVERALL_SCORE, TOTAL_LATENCY_MS
            FROM SECSIGNAL.EVALUATION.EVAL_RUNS
            ORDER BY STARTED_AT DESC
            LIMIT 2
        """)
        rows = cursor.fetchall()

        if len(rows) < 2:
            print("Need at least 2 runs to compare. Only found:", len(rows))
            return

        cols = [desc[0] for desc in cursor.description]
        current = dict(zip(cols, rows[0]))
        previous = dict(zip(cols, rows[1]))

        print(f"\n{'='*70}")
        print("  RUN COMPARISON")
        print(f"{'='*70}")
        print(f"  Current:  {current['RUN_ID'][:8]}... ({current['STARTED_AT']})")
        print(f"  Previous: {previous['RUN_ID'][:8]}... ({previous['STARTED_AT']})")
        print()

        dimensions = [
            ("Routing", "AVG_ROUTING_SCORE"),
            ("Retrieval", "AVG_RETRIEVAL_SCORE"),
            ("Answer Quality", "AVG_ANSWER_SCORE"),
            ("Faithfulness", "AVG_FAITHFULNESS_SCORE"),
            ("OVERALL", "AVG_OVERALL_SCORE"),
        ]

        print(f"  {'Dimension':<20} {'Previous':>10} {'Current':>10} {'Delta':>10}")
        print(f"  {'-'*20} {'-'*10} {'-'*10} {'-'*10}")

        for name, col in dimensions:
            prev_val = previous.get(col, 0) or 0
            curr_val = current.get(col, 0) or 0
            delta = curr_val - prev_val
            arrow = "+" if delta > 0 else ""
            print(f"  {name:<20} {prev_val:>10.2f} {curr_val:>10.2f} {arrow}{delta:>9.2f}")

        prev_lat = previous.get("TOTAL_LATENCY_MS", 0) or 0
        curr_lat = current.get("TOTAL_LATENCY_MS", 0) or 0
        print(f"\n  Latency: {prev_lat / 1000:.1f}s → {curr_lat / 1000:.1f}s")
        print(f"{'='*70}\n")

    finally:
        cursor.close()
