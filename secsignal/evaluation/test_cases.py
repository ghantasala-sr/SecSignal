"""Curated evaluation test cases for the SecSignal agent system.

Each test case defines:
  - id: unique identifier
  - category: trend | comparison | anomaly | followup
  - query: the user question
  - expected_query_type: what the supervisor should classify it as
  - expected_tickers: tickers the supervisor should extract
  - expected_topics: keywords that should appear in a good answer
  - context: optional prior conversation turns (for follow-up tests)
  - description: human-readable explanation of what this tests
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TestCase:
    id: str
    category: str
    query: str
    expected_query_type: str
    expected_tickers: list[str]
    expected_topics: list[str]
    context: list[dict[str, str]] = field(default_factory=list)
    description: str = ""


# ---------------------------------------------------------------------------
# Trend test cases (6) — single-company temporal analysis
# ---------------------------------------------------------------------------

TREND_CASES = [
    TestCase(
        id="trend_01",
        category="trend",
        query="How have Apple's risk factor disclosures changed over recent filings?",
        expected_query_type="trend",
        expected_tickers=["AAPL"],
        expected_topics=["risk", "factor", "change", "filing"],
        description="Basic trend query — single ticker, risk factors over time",
    ),
    TestCase(
        id="trend_02",
        category="trend",
        query="What are the key financial trends for NVDA?",
        expected_query_type="trend",
        expected_tickers=["NVDA"],
        expected_topics=["revenue", "financial", "trend"],
        description="Financial trend query with explicit ticker symbol",
    ),
    TestCase(
        id="trend_03",
        category="trend",
        query="Show me Tesla's filing history and any changes in their disclosures",
        expected_query_type="trend",
        expected_tickers=["TSLA"],
        expected_topics=["filing", "disclosure", "Tesla"],
        description="Trend query using company name instead of ticker",
    ),
    TestCase(
        id="trend_04",
        category="trend",
        query="How has Microsoft's risk profile evolved in their SEC filings?",
        expected_query_type="trend",
        expected_tickers=["MSFT"],
        expected_topics=["risk", "Microsoft", "filing"],
        description="Trend query with 'evolved' language implying temporal analysis",
    ),
    TestCase(
        id="trend_05",
        category="trend",
        query="What does Google's latest 10-K say about competition risks?",
        expected_query_type="trend",
        expected_tickers=["GOOGL"],
        expected_topics=["competition", "risk", "10-K"],
        description="Specific filing type query — tests extraction from search corpus",
    ),
    TestCase(
        id="trend_06",
        category="trend",
        query="Summarize Amazon's financial performance from their recent filings",
        expected_query_type="trend",
        expected_tickers=["AMZN"],
        expected_topics=["financial", "performance", "Amazon"],
        description="Broad financial summary — tests integration of multiple data sources",
    ),
]

# ---------------------------------------------------------------------------
# Comparison test cases (5) — multi-company analysis
# ---------------------------------------------------------------------------

COMPARISON_CASES = [
    TestCase(
        id="comp_01",
        category="comparison",
        query="Compare Apple and Microsoft's risk factor disclosures",
        expected_query_type="comparison",
        expected_tickers=["AAPL", "MSFT"],
        expected_topics=["risk", "factor", "Apple", "Microsoft"],
        description="Two-company risk comparison with company names",
    ),
    TestCase(
        id="comp_02",
        category="comparison",
        query="How do NVDA and TSLA compare in their SEC filings?",
        expected_query_type="comparison",
        expected_tickers=["NVDA", "TSLA"],
        expected_topics=["filing", "compare"],
        description="Two-ticker comparison with explicit ticker symbols",
    ),
    TestCase(
        id="comp_03",
        category="comparison",
        query="Compare the financial disclosures of AAPL, GOOGL, and AMZN",
        expected_query_type="comparison",
        expected_tickers=["AAPL", "GOOGL", "AMZN"],
        expected_topics=["financial", "disclosure"],
        description="Three-company comparison — tests multi-ticker extraction",
    ),
    TestCase(
        id="comp_04",
        category="comparison",
        query="Which company has more risk factors in their filings, Apple or Tesla?",
        expected_query_type="comparison",
        expected_tickers=["AAPL", "TSLA"],
        expected_topics=["risk", "factor"],
        description="Comparative question with 'which' framing",
    ),
    TestCase(
        id="comp_05",
        category="comparison",
        query="Side by side comparison of MSFT and GOOGL filing trends",
        expected_query_type="comparison",
        expected_tickers=["MSFT", "GOOGL"],
        expected_topics=["comparison", "trend", "filing"],
        description="Explicit 'side by side' comparison language",
    ),
]

# ---------------------------------------------------------------------------
# Anomaly test cases (4) — unusual patterns / outlier detection
# ---------------------------------------------------------------------------

ANOMALY_CASES = [
    TestCase(
        id="anom_01",
        category="anomaly",
        query="Are there any unusual changes in risk factor disclosures across tech companies?",
        expected_query_type="anomaly",
        expected_tickers=[],  # broad query, no specific ticker
        expected_topics=["unusual", "change", "risk"],
        description="Broad anomaly scan across all companies",
    ),
    TestCase(
        id="anom_02",
        category="anomaly",
        query="Detect any red flags or anomalies in Tesla's filings",
        expected_query_type="anomaly",
        expected_tickers=["TSLA"],
        expected_topics=["anomaly", "red flag", "Tesla"],
        description="Single-ticker anomaly detection with 'red flags' language",
    ),
    TestCase(
        id="anom_03",
        category="anomaly",
        query="Has NVDA's risk disclosure changed dramatically in any recent filing?",
        expected_query_type="anomaly",
        expected_tickers=["NVDA"],
        expected_topics=["risk", "disclosure", "change"],
        description="Anomaly query with 'dramatically changed' framing",
    ),
    TestCase(
        id="anom_04",
        category="anomaly",
        query="What are the biggest outliers in financial metrics across all companies?",
        expected_query_type="anomaly",
        expected_tickers=[],
        expected_topics=["outlier", "financial", "metric"],
        description="Broad financial anomaly scan — outlier language",
    ),
]

# ---------------------------------------------------------------------------
# Follow-up / context test cases (5) — multi-turn pronoun resolution
# ---------------------------------------------------------------------------

FOLLOWUP_CASES = [
    TestCase(
        id="follow_01",
        category="followup",
        query="What about Microsoft?",
        expected_query_type="trend",
        expected_tickers=["MSFT"],
        expected_topics=["risk", "Microsoft"],
        context=[
            {"role": "user", "content": "How have Apple's risk factor disclosures changed?"},
            {"role": "assistant", "content": "Apple's risk factors have shown increasing emphasis on regulatory risks and supply chain challenges across recent filings."},
        ],
        description="Follow-up with company name — should inherit trend type from context",
    ),
    TestCase(
        id="follow_02",
        category="followup",
        query="Now compare that with Tesla",
        expected_query_type="comparison",
        expected_tickers=["AAPL", "TSLA"],
        expected_topics=["compare", "risk"],
        context=[
            {"role": "user", "content": "How have Apple's risk factor disclosures changed?"},
            {"role": "assistant", "content": "Apple's risk factors have shown increasing emphasis on regulatory risks."},
        ],
        description="Follow-up that shifts to comparison — should resolve 'that' to AAPL",
    ),
    TestCase(
        id="follow_03",
        category="followup",
        query="Any anomalies there?",
        expected_query_type="anomaly",
        expected_tickers=["NVDA"],
        expected_topics=["anomaly"],
        context=[
            {"role": "user", "content": "What are the key financial trends for NVDA?"},
            {"role": "assistant", "content": "NVDA has shown strong revenue growth driven by AI demand."},
        ],
        description="Follow-up anomaly query — should resolve 'there' to NVDA",
    ),
    TestCase(
        id="follow_04",
        category="followup",
        query="How does GOOGL compare?",
        expected_query_type="comparison",
        expected_tickers=["AMZN", "GOOGL"],
        expected_topics=["compare"],
        context=[
            {"role": "user", "content": "Summarize Amazon's financial performance from their recent filings"},
            {"role": "assistant", "content": "Amazon's recent filings show continued growth in cloud services."},
        ],
        description="Follow-up comparison — should combine AMZN from context with GOOGL",
    ),
    TestCase(
        id="follow_05",
        category="followup",
        query="Tell me more about their supply chain risks",
        expected_query_type="trend",
        expected_tickers=["TSLA"],
        expected_topics=["supply chain", "risk"],
        context=[
            {"role": "user", "content": "Detect any red flags in Tesla's filings"},
            {"role": "assistant", "content": "Tesla's filings show notable changes in supply chain and manufacturing risk disclosures."},
        ],
        description="Follow-up drilling deeper — should resolve 'their' to TSLA",
    ),
]

# ---------------------------------------------------------------------------
# Combined list of all test cases
# ---------------------------------------------------------------------------

ALL_TEST_CASES: list[TestCase] = (
    TREND_CASES + COMPARISON_CASES + ANOMALY_CASES + FOLLOWUP_CASES
)

CASES_BY_CATEGORY: dict[str, list[TestCase]] = {
    "trend": TREND_CASES,
    "comparison": COMPARISON_CASES,
    "anomaly": ANOMALY_CASES,
    "followup": FOLLOWUP_CASES,
}


def get_test_cases(category: str | None = None) -> list[TestCase]:
    """Return test cases, optionally filtered by category."""
    if category is None:
        return ALL_TEST_CASES
    return CASES_BY_CATEGORY.get(category, [])
