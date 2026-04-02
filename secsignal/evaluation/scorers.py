"""Evaluation scorers for the SecSignal agent system.

Four scoring dimensions, each returning a float 1-5:
  1. Routing accuracy  — exact-match on query_type + ticker extraction
  2. Retrieval quality — heuristic check on retrieved chunks
  3. Answer quality    — LLM-as-judge via Cortex COMPLETE
  4. Faithfulness      — LLM-as-judge hallucination check via Cortex COMPLETE

The LLM-as-judge prompts enforce: "only generate answers from the cited sources,
do not hallucinate."
"""

from __future__ import annotations

import json
import os
from typing import Any

import structlog

from secsignal.agents.connection import get_snowflake_connection
from secsignal.evaluation.test_cases import TestCase

logger = structlog.get_logger(__name__)

LLM_MODEL = os.environ.get("CORTEX_LLM_MODEL", "claude-sonnet-4-6")


# ---------------------------------------------------------------------------
# 1. Routing scorer — deterministic exact match
# ---------------------------------------------------------------------------

def score_routing(test_case: TestCase, result: dict[str, Any]) -> dict[str, Any]:
    """Score the supervisor's classification accuracy.

    Returns:
        Dict with score (1-5), details about type match and ticker overlap.
    """
    actual_type = result.get("query_type", "general")
    expected_type = test_case.expected_query_type

    actual_tickers = sorted(set(result.get("tickers", [])))
    expected_tickers = sorted(set(test_case.expected_tickers))

    # Query type match: 0 or 1
    type_match = actual_type == expected_type

    # Ticker overlap: Jaccard similarity
    if expected_tickers or actual_tickers:
        expected_set = set(expected_tickers)
        actual_set = set(actual_tickers)
        intersection = expected_set & actual_set
        union = expected_set | actual_set
        ticker_score = len(intersection) / len(union) if union else 1.0
    else:
        # Both empty — perfect match
        ticker_score = 1.0

    # Combined score: type match is 60%, ticker match is 40%
    raw_score = (0.6 * float(type_match)) + (0.4 * ticker_score)
    # Map 0-1 to 1-5 scale
    score = 1.0 + raw_score * 4.0

    return {
        "score": round(score, 2),
        "type_match": type_match,
        "expected_type": expected_type,
        "actual_type": actual_type,
        "ticker_overlap": round(ticker_score, 2),
        "expected_tickers": expected_tickers,
        "actual_tickers": actual_tickers,
    }


# ---------------------------------------------------------------------------
# 2. Retrieval scorer — heuristic based on chunk relevance
# ---------------------------------------------------------------------------

def score_retrieval(test_case: TestCase, result: dict[str, Any]) -> dict[str, Any]:
    """Score the quality of retrieved chunks.

    Heuristics:
      - Were chunks retrieved at all?
      - Do retrieved chunks mention expected tickers?
      - Do retrieved chunks mention expected topics?
      - Is the source count reasonable (not empty, not excessive)?
    """
    chunks = result.get("retrieved_chunks", [])
    sources = result.get("sources", [])
    expected_tickers = set(test_case.expected_tickers)

    if not chunks and not sources:
        return {
            "score": 1.0,
            "reason": "No chunks or sources retrieved",
            "chunk_count": 0,
            "source_count": 0,
            "ticker_coverage": 0.0,
            "topic_coverage": 0.0,
        }

    # Ticker coverage: what fraction of expected tickers appear in sources?
    source_tickers = set()
    for s in sources:
        t = s.get("ticker", "")
        if t:
            source_tickers.add(t)
    if expected_tickers:
        ticker_coverage = len(expected_tickers & source_tickers) / len(expected_tickers)
    else:
        # No specific tickers expected — any retrieval is fine
        ticker_coverage = 1.0 if sources else 0.0

    # Topic coverage: what fraction of expected topics appear in the answer?
    answer = result.get("final_answer", "").lower()
    expected_topics = test_case.expected_topics
    if expected_topics:
        topic_hits = sum(1 for t in expected_topics if t.lower() in answer)
        topic_coverage = topic_hits / len(expected_topics)
    else:
        topic_coverage = 1.0

    # Chunk count penalty: 0 chunks is bad, 1-15 is good, >20 is slightly noisy
    chunk_count = len(chunks)
    if chunk_count == 0:
        count_score = 0.0
    elif chunk_count <= 15:
        count_score = 1.0
    else:
        count_score = max(0.5, 1.0 - (chunk_count - 15) * 0.02)

    # Weighted combination
    raw = 0.4 * ticker_coverage + 0.35 * topic_coverage + 0.25 * count_score
    score = 1.0 + raw * 4.0

    return {
        "score": round(score, 2),
        "chunk_count": chunk_count,
        "source_count": len(sources),
        "ticker_coverage": round(ticker_coverage, 2),
        "topic_coverage": round(topic_coverage, 2),
        "count_score": round(count_score, 2),
    }


# ---------------------------------------------------------------------------
# 3. Answer quality scorer — LLM-as-judge
# ---------------------------------------------------------------------------

ANSWER_QUALITY_PROMPT = """You are an evaluation judge for a financial analysis system that answers questions about SEC filings. Your job is to score the quality of a generated answer.

IMPORTANT: You must only evaluate based on the evidence provided. Do NOT use your own knowledge. Do NOT hallucinate or infer information that is not in the provided context.

**User Query:** {query}

**Generated Answer:**
{answer}

**Available Sources:**
{sources}

Score the answer on these criteria (1-5 each):

1. **Correctness** (1-5): Are the claims in the answer supported by the provided sources? Penalize any claim that cannot be traced back to the sources. A score of 1 means mostly unsupported claims. A score of 5 means every claim is source-backed.

2. **Specificity** (1-5): Does the answer cite specific numbers, dates, ticker symbols, and filing types? A score of 1 means vague generalities. A score of 5 means precise data points throughout.

3. **Structure** (1-5): Is the answer well-organized with headers, tables, and clear sections? A score of 1 means unstructured wall of text. A score of 5 means clear markdown structure with tables where appropriate.

4. **Relevance** (1-5): Does the answer directly address the user's question? A score of 1 means off-topic. A score of 5 means precisely on-topic.

Output ONLY valid JSON with this exact structure:
{{
  "correctness": <int 1-5>,
  "specificity": <int 1-5>,
  "structure": <int 1-5>,
  "relevance": <int 1-5>,
  "reasoning": "<brief explanation of scores, cite specific examples>"
}}"""


def score_answer_quality(test_case: TestCase, result: dict[str, Any]) -> dict[str, Any]:
    """Score answer quality using LLM-as-judge via Cortex COMPLETE.

    Evaluates correctness, specificity, structure, and relevance.
    """
    answer = result.get("final_answer", "")
    if not answer or answer.startswith("An error occurred"):
        return {
            "score": 1.0,
            "correctness": 1,
            "specificity": 1,
            "structure": 1,
            "relevance": 1,
            "reasoning": "No valid answer generated",
        }

    sources = result.get("sources", [])
    sources_text = _format_sources_for_judge(sources)

    prompt = ANSWER_QUALITY_PROMPT.format(
        query=test_case.query,
        answer=answer[:3000],  # Truncate to avoid prompt overflow
        sources=sources_text,
    )

    scores = _call_llm_judge(prompt)

    # Average the 4 sub-scores
    sub_scores = [
        scores.get("correctness", 3),
        scores.get("specificity", 3),
        scores.get("structure", 3),
        scores.get("relevance", 3),
    ]
    avg = sum(sub_scores) / len(sub_scores)

    return {
        "score": round(avg, 2),
        "correctness": scores.get("correctness", 3),
        "specificity": scores.get("specificity", 3),
        "structure": scores.get("structure", 3),
        "relevance": scores.get("relevance", 3),
        "reasoning": scores.get("reasoning", ""),
    }


# ---------------------------------------------------------------------------
# 4. Faithfulness scorer — LLM-as-judge hallucination check
# ---------------------------------------------------------------------------

FAITHFULNESS_PROMPT = """You are a strict faithfulness evaluator for a financial analysis system. Your ONLY job is to check whether the generated answer is faithful to the provided source material.

CRITICAL RULE: The answer must ONLY contain information that can be directly traced back to the cited sources. Any claim, number, date, or assertion that is NOT present in the sources is a HALLUCINATION and must be penalized severely.

**User Query:** {query}

**Generated Answer:**
{answer}

**Source Material (the ONLY valid basis for claims in the answer):**
{context}

Evaluate faithfulness on a 1-5 scale:

- **5 (Fully Faithful):** Every claim in the answer is directly supported by the source material. No hallucinated facts, numbers, or assertions.
- **4 (Mostly Faithful):** Nearly all claims are supported. Minor extrapolations that are reasonable given the data but not explicitly stated.
- **3 (Partially Faithful):** Some claims are supported, but the answer includes several assertions not found in the sources.
- **2 (Mostly Unfaithful):** The answer contains many claims that cannot be verified from the sources. Significant hallucination.
- **1 (Unfaithful):** The answer is largely fabricated with little connection to the actual source material.

For each unsupported claim you find, list it explicitly.

Output ONLY valid JSON with this exact structure:
{{
  "faithfulness_score": <int 1-5>,
  "unsupported_claims": ["<claim 1>", "<claim 2>", ...],
  "supported_claim_count": <int>,
  "total_claim_count": <int>,
  "reasoning": "<explanation citing specific examples of supported and unsupported claims>"
}}"""


def score_faithfulness(test_case: TestCase, result: dict[str, Any]) -> dict[str, Any]:
    """Score answer faithfulness — checks for hallucination.

    Uses LLM-as-judge to verify every claim in the answer is grounded
    in the retrieved sources. Enforces: only generate answers from
    cited sources, do not hallucinate.
    """
    answer = result.get("final_answer", "")
    if not answer or answer.startswith("An error occurred"):
        return {
            "score": 1.0,
            "faithfulness_score": 1,
            "unsupported_claims": [],
            "supported_claim_count": 0,
            "total_claim_count": 0,
            "reasoning": "No valid answer generated",
        }

    # Build the full context that was available to the synthesizer
    context_parts = []

    # Text chunks
    for i, chunk in enumerate(result.get("retrieved_chunks", []), 1):
        context_parts.append(
            f"[Source {i}] ({chunk.get('ticker', '?')} | {chunk.get('filing_type', '?')} | "
            f"{chunk.get('filing_date', '?')})\n{chunk.get('content', '')[:600]}"
        )

    # SQL results
    for r in result.get("sql_results", []):
        context_parts.append(f"[SQL Data] {json.dumps(r, default=str)[:300]}")

    # Anomaly scores
    for a in result.get("anomaly_scores", []):
        context_parts.append(
            f"[Anomaly] {a.get('ticker', '?')} ({a.get('filing_date', '?')}): "
            f"{a.get('metric', '?')} z={a.get('z_score', 0):.2f}"
        )

    # Web context
    web_ctx = result.get("web_context", "")
    if web_ctx:
        context_parts.append(f"[Web Search]\n{web_ctx[:1000]}")

    context = "\n\n".join(context_parts) if context_parts else "No source material was retrieved."

    prompt = FAITHFULNESS_PROMPT.format(
        query=test_case.query,
        answer=answer[:3000],
        context=context[:4000],  # Limit context to avoid prompt overflow
    )

    scores = _call_llm_judge(prompt)

    faith_score = scores.get("faithfulness_score", 3)
    # Clamp to 1-5
    faith_score = max(1, min(5, faith_score))

    return {
        "score": float(faith_score),
        "faithfulness_score": faith_score,
        "unsupported_claims": scores.get("unsupported_claims", []),
        "supported_claim_count": scores.get("supported_claim_count", 0),
        "total_claim_count": scores.get("total_claim_count", 0),
        "reasoning": scores.get("reasoning", ""),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_sources_for_judge(sources: list[dict[str, str]]) -> str:
    """Format source citations for judge prompts."""
    if not sources:
        return "No sources cited."
    parts = []
    for s in sources:
        parts.append(
            f"- {s.get('ticker', '?')} | {s.get('filing_type', '?')} | "
            f"{s.get('filing_date', '?')} | {s.get('content_type', '?')}"
        )
    return "\n".join(parts)


def _call_llm_judge(prompt: str) -> dict[str, Any]:
    """Call Cortex COMPLETE and parse the JSON response."""
    conn = get_snowflake_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT SNOWFLAKE.CORTEX.COMPLETE(%s, %s) AS response",
            (LLM_MODEL, prompt),
        )
        row = cursor.fetchone()
        raw = row[0] if row else "{}"

        # Strip markdown code fences if present
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        return json.loads(text)
    except (json.JSONDecodeError, Exception) as exc:
        logger.warning("llm_judge_parse_failed", error=str(exc), raw=raw[:200] if 'raw' in dir() else "")
        return {}
    finally:
        cursor.close()


# ---------------------------------------------------------------------------
# Composite scorer — runs all four and returns overall
# ---------------------------------------------------------------------------

def score_all(test_case: TestCase, result: dict[str, Any]) -> dict[str, Any]:
    """Run all four scorers and compute an overall weighted score.

    Weights:
      - Routing:      15%  (infrastructure correctness)
      - Retrieval:    20%  (data quality)
      - Answer:       30%  (output quality)
      - Faithfulness: 35%  (trust — highest weight per user requirement)
    """
    routing = score_routing(test_case, result)
    retrieval = score_retrieval(test_case, result)
    answer = score_answer_quality(test_case, result)
    faithfulness = score_faithfulness(test_case, result)

    overall = (
        0.15 * routing["score"]
        + 0.20 * retrieval["score"]
        + 0.30 * answer["score"]
        + 0.35 * faithfulness["score"]
    )

    return {
        "routing": routing,
        "retrieval": retrieval,
        "answer_quality": answer,
        "faithfulness": faithfulness,
        "overall_score": round(overall, 2),
    }
