"""Peer-group agent — sector-wide comparison across the available ticker universe.

Since SIC codes are NULL in RAW_COMPANIES, uses a hardcoded sector mapping
for the 6 tickers in the database plus LLM-based peer identification.
Pulls financial metrics for all peers and generates comparison charts.
"""

from __future__ import annotations

import json
import os

import structlog

from secsignal.agents.state import FilingState
from secsignal.agents.tools.sql_tool import query_extracted_financials
from secsignal.agents.tools.semantic_tool import search_filing_text
from secsignal.agents.connection import get_snowflake_connection

logger = structlog.get_logger(__name__)

LLM_MODEL = os.environ.get("CORTEX_LLM_MODEL", "claude-sonnet-4-6")

# Hardcoded sector mapping since SIC_CODE is NULL for all companies
SECTOR_MAP = {
    "AAPL": {"sector": "Consumer Electronics / Tech Hardware", "sub": "Devices & Services"},
    "MSFT": {"sector": "Enterprise Software / Cloud", "sub": "Cloud & Productivity"},
    "GOOGL": {"sector": "Digital Advertising / Cloud", "sub": "Search & Cloud"},
    "AMZN": {"sector": "E-Commerce / Cloud", "sub": "Retail & AWS"},
    "NVDA": {"sector": "Semiconductors / AI Hardware", "sub": "GPU & Data Center"},
    "TSLA": {"sector": "Electric Vehicles / Energy", "sub": "EV & Storage"},
}

# Peer groups: which tickers are natural comparisons
PEER_GROUPS = {
    "mega_cap_tech": ["AAPL", "MSFT", "GOOGL", "AMZN"],
    "cloud_platforms": ["MSFT", "GOOGL", "AMZN"],
    "ai_leaders": ["NVDA", "MSFT", "GOOGL", "AMZN"],
    "growth_disruptors": ["NVDA", "TSLA", "AMZN"],
    "hardware": ["AAPL", "NVDA"],
    "all": ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA"],
}

PEER_ID_PROMPT = """Given these available tickers and their sectors:
{sector_info}

And the user query: "{query}"
About ticker(s): {tickers}

Which peer group is most relevant? Choose ONE from: {groups}
Also list the specific tickers to compare (from the available set only).

Output ONLY a JSON object:
{{
  "peer_group": "group_name",
  "tickers": ["TICKER1", "TICKER2", ...],
  "rationale": "one sentence why"
}}

Output ONLY valid JSON, no markdown."""


def peer_group_agent(state: FilingState) -> dict:
    """Compare a ticker against its sector peers.

    1. Identify the relevant peer group using LLM + hardcoded mappings
    2. Pull financial metrics for all peers
    3. Generate cross-peer comparison charts
    """
    query = state["query"]
    tickers = state.get("tickers", [])

    if not tickers:
        tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA"]

    conn = get_snowflake_connection()
    cursor = conn.cursor()

    sql_results = []
    retrieved_chunks = []
    generated_charts = []

    try:
        # Step 1: Identify peer group
        peer_tickers = _identify_peers(cursor, query, tickers)

        # Step 2: Pull metrics for all peers
        peer_metrics = []
        for ticker in peer_tickers:
            metrics = _get_peer_metrics(ticker)
            if metrics:
                peer_metrics.append(metrics)
                sql_results.append({
                    "source": "peer_financials",
                    "ticker": ticker,
                    "filing_date": metrics.get("latest_filing_date", ""),
                    **{k: v for k, v in metrics.items() if k != "latest_filing_date"},
                })

        # Step 3: Semantic search for peer context
        try:
            chunks = search_filing_text(
                query=f"competitive landscape market position industry comparison {query}",
                ticker=tickers[0] if len(tickers) == 1 else None,
                limit=5,
            )
            for chunk in chunks:
                retrieved_chunks.append({
                    "content": chunk["content"],
                    "ticker": chunk["ticker"],
                    "filing_type": chunk["filing_type"],
                    "filing_date": chunk["filing_date"],
                    "content_type": chunk["content_type"],
                    "score": chunk["score"],
                })
        except Exception:
            logger.exception("peer_semantic_failed")

        # Step 4: Generate comparison charts
        if len(peer_metrics) >= 2:
            generated_charts.extend(_build_peer_charts(peer_metrics))

    except Exception:
        logger.exception("peer_group_agent_failed")
    finally:
        cursor.close()

    logger.info(
        "peer_group_agent_done",
        tickers=tickers,
        peer_count=len(sql_results),
        charts=len(generated_charts),
    )

    return {
        "sql_results": sql_results,
        "retrieved_chunks": retrieved_chunks,
        "retrieved_charts": [],
        "generated_charts": generated_charts,
    }


def _identify_peers(cursor, query: str, tickers: list[str]) -> list[str]:
    """Identify the relevant peer group using LLM."""
    sector_info = "\n".join(
        f"- {t}: {info['sector']} ({info['sub']})" for t, info in SECTOR_MAP.items()
    )
    groups = ", ".join(PEER_GROUPS.keys())

    prompt = PEER_ID_PROMPT.format(
        sector_info=sector_info,
        query=query,
        tickers=", ".join(tickers),
        groups=groups,
    )

    try:
        cursor.execute(
            "SELECT SNOWFLAKE.CORTEX.COMPLETE(%s, %s) AS response",
            (LLM_MODEL, prompt),
        )
        row = cursor.fetchone()
        if row and row[0]:
            raw = row[0].strip()
            if raw.startswith("```"):
                lines = raw.split("\n")
                raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            result = json.loads(raw)
            peer_tickers = result.get("tickers", [])
            # Validate tickers exist in our universe
            valid = [t for t in peer_tickers if t in SECTOR_MAP]
            if valid:
                return valid
    except (json.JSONDecodeError, Exception):
        logger.exception("peer_identification_failed")

    # Fallback: use the all group or derive from target ticker
    if len(tickers) == 1 and tickers[0] in SECTOR_MAP:
        target = tickers[0]
        # Find groups containing the target
        for group_name, group_tickers in PEER_GROUPS.items():
            if target in group_tickers and group_name != "all":
                return group_tickers
    return list(SECTOR_MAP.keys())


def _get_peer_metrics(ticker: str) -> dict | None:
    """Get key financial metrics for a peer ticker."""
    conn = get_snowflake_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT METRIC_NAME, VALUE, FILING_DATE
            FROM SECSIGNAL.RAW.EXTRACTED_FINANCIALS
            WHERE TICKER = %s
              AND METRIC_CATEGORY IN ('revenue', 'income', 'margin', 'growth')
            ORDER BY FILING_DATE DESC
            LIMIT 15
            """,
            (ticker.upper(),),
        )
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        if not rows:
            return None

        metrics_map: dict[str, float] = {}
        latest_date = ""
        for row in rows:
            if not latest_date:
                latest_date = str(row.get("FILING_DATE", ""))
            name = row["METRIC_NAME"]
            val = row.get("VALUE")
            if val is not None and name not in metrics_map:
                metrics_map[name] = float(val)

        return {
            "ticker": ticker.upper(),
            "latest_filing_date": latest_date,
            "total_revenue_m": metrics_map.get("Total Revenue", metrics_map.get("Revenue", 0)),
            "net_income_m": metrics_map.get("Net Income", metrics_map.get("Net income", 0)),
            "operating_income_m": metrics_map.get("Operating Income", metrics_map.get("Operating income", 0)),
            "revenue_growth_pct": metrics_map.get("Total Revenue Growth", metrics_map.get("Revenue Growth", 0)),
            "gross_margin_pct": metrics_map.get("Gross Margin", metrics_map.get("Gross margin", 0)),
            "operating_margin_pct": metrics_map.get("Operating Margin", 0),
        }
    except Exception:
        logger.exception("get_peer_metrics_failed", ticker=ticker)
        return None
    finally:
        cursor.close()


def _build_peer_charts(metrics: list[dict]) -> list[dict]:
    """Build peer comparison charts."""
    charts = []
    tickers_str = ", ".join(m["ticker"] for m in metrics)

    # Revenue comparison bar chart
    rev_data = [
        {"label": m["ticker"], "value": round(m.get("total_revenue_m", 0), 1)}
        for m in metrics if m.get("total_revenue_m")
    ]
    if rev_data:
        charts.append({
            "chart_type": "bar",
            "title": "Peer Group Revenue Comparison ($M)",
            "category": "peer_comparison",
            "unit": "USD_millions",
            "ticker": tickers_str,
            "data": rev_data,
        })

    # Growth comparison bar chart
    growth_data = [
        {"label": m["ticker"], "value": round(m.get("revenue_growth_pct", 0), 1)}
        for m in metrics if m.get("revenue_growth_pct")
    ]
    if growth_data:
        charts.append({
            "chart_type": "bar",
            "title": "Peer Group Revenue Growth (%)",
            "category": "peer_comparison",
            "unit": "percent",
            "ticker": tickers_str,
            "data": growth_data,
        })

    # Radar chart comparing financial profiles
    radar_data = []
    for m in metrics:
        entry = {"label": m["ticker"]}
        entry["Gross Margin"] = round(m.get("gross_margin_pct", 0), 1)
        entry["Op Margin"] = round(m.get("operating_margin_pct", 0), 1)
        entry["Rev Growth"] = round(m.get("revenue_growth_pct", 0), 1)
        # Normalize revenue to a 0-100 scale for radar visibility
        max_rev = max((x.get("total_revenue_m", 1) for x in metrics), default=1)
        entry["Revenue Scale"] = round((m.get("total_revenue_m", 0) / max_rev) * 100, 1) if max_rev else 0
        radar_data.append(entry)

    if radar_data:
        charts.append({
            "chart_type": "radar",
            "title": "Peer Group Financial Profile",
            "category": "peer_comparison",
            "unit": "mixed",
            "ticker": tickers_str,
            "data": radar_data,
            "series": [
                {"key": "Gross Margin", "name": "Gross Margin %", "color": "#5eadad"},
                {"key": "Op Margin", "name": "Op Margin %", "color": "#3B82F6"},
                {"key": "Rev Growth", "name": "Rev Growth %", "color": "#10B981"},
                {"key": "Revenue Scale", "name": "Revenue (scaled)", "color": "#F59E0B"},
            ],
        })

    return charts
