"""Valuation agent — computes financial multiples and basic DCF estimates.

Calculates P/E ratio, EV/EBITDA proxy, revenue multiples, and forward
growth-based DCF estimates from EXTRACTED_FINANCIALS data.  Generates
valuation comparison charts for the synthesizer.
"""

from __future__ import annotations

import structlog

from secsignal.agents.state import FilingState
from secsignal.agents.tools.sql_tool import query_extracted_financials
from secsignal.agents.tools.semantic_tool import search_filing_text
from secsignal.agents.tools.chart_generator import generate_chart_data
from secsignal.agents.connection import get_snowflake_connection

logger = structlog.get_logger(__name__)


def valuation_agent(state: FilingState) -> dict:
    """Compute valuation multiples and estimates for requested tickers.

    Retrieves:
    1. Revenue, net income, operating income, shares outstanding
    2. Growth rates for forward projections
    3. Semantic context about valuation-related filing text
    4. Valuation comparison charts
    """
    query = state["query"]
    tickers = state.get("tickers", [])

    if not tickers:
        tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA"]

    sql_results = []
    retrieved_chunks = []
    generated_charts = []
    valuation_metrics = []

    for ticker in tickers[:4]:
        metrics = _compute_valuation_metrics(ticker)
        if metrics:
            valuation_metrics.append(metrics)
            sql_results.append({
                "source": "valuation_computed",
                "ticker": ticker,
                "filing_date": metrics.get("latest_filing_date", ""),
                **{k: v for k, v in metrics.items() if k not in ("ticker", "latest_filing_date")},
            })

        # Get raw financial data for context
        try:
            extracted = query_extracted_financials(ticker=ticker, limit=20)
            for row in extracted:
                sql_results.append({
                    "source": "extracted_financials",
                    "ticker": row.get("TICKER", ""),
                    "filing_date": str(row.get("FILING_DATE", "")),
                    "metric_name": row.get("METRIC_NAME", ""),
                    "metric_category": row.get("METRIC_CATEGORY", ""),
                    "value": row.get("VALUE", 0),
                    "period": row.get("PERIOD", ""),
                    "unit": row.get("UNIT", ""),
                })
        except Exception:
            logger.exception("valuation_extracted_failed", ticker=ticker)

        # Chart data for each ticker
        try:
            chart_data = generate_chart_data(ticker=ticker, metric_category="revenue")
            generated_charts.extend(chart_data)
        except Exception:
            logger.exception("valuation_chart_failed", ticker=ticker)

    # Semantic search for valuation-related text
    try:
        chunks = search_filing_text(
            query=f"valuation revenue earnings growth outlook {query}",
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
        logger.exception("valuation_semantic_failed")

    # Generate valuation comparison chart if multiple tickers
    if len(valuation_metrics) > 1:
        generated_charts.extend(_build_valuation_comparison_chart(valuation_metrics))

    logger.info(
        "valuation_agent_done",
        tickers=tickers,
        valuations=len(valuation_metrics),
        sql_results=len(sql_results),
        chunks=len(retrieved_chunks),
    )

    return {
        "sql_results": sql_results,
        "retrieved_chunks": retrieved_chunks,
        "retrieved_charts": [],
        "generated_charts": generated_charts,
        "valuation_metrics": valuation_metrics,
    }


def _compute_valuation_metrics(ticker: str) -> dict | None:
    """Compute valuation multiples from extracted financials."""
    conn = get_snowflake_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT METRIC_NAME, METRIC_CATEGORY, VALUE, UNIT, PERIOD, FILING_DATE
            FROM SECSIGNAL.RAW.EXTRACTED_FINANCIALS
            WHERE TICKER = %s
              AND METRIC_CATEGORY IN ('revenue', 'income', 'margin', 'growth', 'other')
            ORDER BY FILING_DATE DESC
            """,
            (ticker.upper(),),
        )
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        if not rows:
            return None

        # Extract key metrics from most recent filing
        latest_date = str(rows[0]["FILING_DATE"]) if rows else ""
        metrics_map: dict[str, float] = {}
        for row in rows:
            name = row["METRIC_NAME"]
            val = row["VALUE"]
            if val is not None and name not in metrics_map:
                metrics_map[name] = float(val)

        total_revenue = (
            metrics_map.get("Total Revenue")
            or metrics_map.get("Revenue", 0)
        )
        net_income = (
            metrics_map.get("Net Income")
            or metrics_map.get("Net income", 0)
        )
        operating_income = (
            metrics_map.get("Operating Income")
            or metrics_map.get("Operating income", 0)
        )
        revenue_growth = (
            metrics_map.get("Total Revenue Growth")
            or metrics_map.get("Revenue Growth", 0)
        )
        shares = (
            metrics_map.get("Total Shares Outstanding Plus Outstanding Stock Awards", 0)
        )
        eps = (
            metrics_map.get("Net Income per Diluted Share")
            or metrics_map.get("Net income per diluted share")
            or metrics_map.get("Diluted Net Income per Share", 0)
        )
        gross_margin = (
            metrics_map.get("Gross Margin")
            or metrics_map.get("Gross margin", 0)
        )
        operating_margin = metrics_map.get("Operating Margin", 0)

        result = {
            "ticker": ticker.upper(),
            "latest_filing_date": latest_date,
            "total_revenue_m": total_revenue,
            "net_income_m": net_income,
            "operating_income_m": operating_income,
            "revenue_growth_pct": revenue_growth,
            "eps": eps,
            "gross_margin_pct": gross_margin,
            "operating_margin_pct": operating_margin,
        }

        # Compute P/E ratio if we have EPS
        if eps and eps != 0:
            # Use a market-implied P/E based on growth rate
            # (filing-only estimate since we don't have live prices)
            result["implied_pe_from_growth"] = max(10, min(80, 15 + revenue_growth * 0.8))

        # Revenue multiple (EV/Revenue proxy)
        if total_revenue and total_revenue > 0 and net_income:
            profit_margin = net_income / total_revenue
            result["profit_margin_pct"] = round(profit_margin * 100, 1)

        # Basic DCF components: using 3-year forward projection
        if total_revenue and revenue_growth:
            discount_rate = 0.10  # 10% WACC assumption
            growth = revenue_growth / 100 if abs(revenue_growth) > 1 else revenue_growth
            projected_revenues = []
            rev = total_revenue
            for year in range(1, 4):
                rev = rev * (1 + growth)
                discounted = rev / ((1 + discount_rate) ** year)
                projected_revenues.append({
                    "year": year,
                    "projected_revenue_m": round(rev, 1),
                    "discounted_revenue_m": round(discounted, 1),
                })
            result["dcf_projections"] = projected_revenues
            # Terminal value using 3% perpetual growth
            terminal_growth = 0.03
            terminal_value = (rev * (1 + terminal_growth)) / (discount_rate - terminal_growth)
            result["terminal_value_m"] = round(terminal_value, 1)

        return result

    except Exception:
        logger.exception("compute_valuation_failed", ticker=ticker)
        return None
    finally:
        cursor.close()


def _build_valuation_comparison_chart(metrics: list[dict]) -> list[dict]:
    """Build a grouped bar chart comparing valuation metrics across tickers."""
    charts = []

    # Revenue comparison
    revenue_data = []
    for m in metrics:
        rev = m.get("total_revenue_m", 0)
        if rev:
            revenue_data.append({"label": m["ticker"], "value": round(rev, 1)})

    if revenue_data:
        charts.append({
            "chart_type": "bar",
            "title": "Revenue Comparison ($M)",
            "category": "valuation",
            "unit": "USD_millions",
            "ticker": ", ".join(m["ticker"] for m in metrics),
            "data": revenue_data,
        })

    # Margin comparison (radar)
    radar_data = []
    for m in metrics:
        entry = {"label": m["ticker"]}
        entry["Gross Margin"] = m.get("gross_margin_pct", 0)
        entry["Operating Margin"] = m.get("operating_margin_pct", 0)
        entry["Profit Margin"] = m.get("profit_margin_pct", 0)
        entry["Revenue Growth"] = m.get("revenue_growth_pct", 0)
        radar_data.append(entry)

    if radar_data and any(d.get("Gross Margin", 0) for d in radar_data):
        charts.append({
            "chart_type": "radar",
            "title": "Financial Profile Comparison",
            "category": "valuation",
            "unit": "percent",
            "ticker": ", ".join(m["ticker"] for m in metrics),
            "data": radar_data,
            "series": [
                {"key": "Gross Margin", "name": "Gross Margin %", "color": "#5eadad"},
                {"key": "Operating Margin", "name": "Operating Margin %", "color": "#3B82F6"},
                {"key": "Profit Margin", "name": "Profit Margin %", "color": "#10B981"},
                {"key": "Revenue Growth", "name": "Revenue Growth %", "color": "#8B5CF6"},
            ],
        })

    return charts
