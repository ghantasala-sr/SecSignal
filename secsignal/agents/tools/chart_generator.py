"""Chart data generator — produces structured data for Streamlit native charts.

Instead of relying on pre-extracted chart images (which are mostly logos),
this tool queries EXTRACTED_FINANCIALS and returns structured data that the
frontend can render using st.bar_chart / st.line_chart / altair.
"""

from __future__ import annotations

from typing import Any

import structlog

from secsignal.agents.connection import get_snowflake_connection

logger = structlog.get_logger(__name__)


def generate_chart_data(
    ticker: str | None = None,
    metric_category: str | None = None,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """Generate chart-ready data from extracted financial metrics.

    Queries EXTRACTED_FINANCIALS and returns structured rows suitable
    for rendering as bar/line charts in Streamlit.

    Args:
        ticker: Filter by ticker. None for all.
        metric_category: Filter by category (e.g. 'revenue', 'income').
        limit: Max data points.

    Returns:
        List of dicts with chart_type, title, data (list of {label, value}).
        Each dict represents one chart to render.
    """
    conn = get_snowflake_connection()
    cursor = conn.cursor()
    try:
        conditions: list[str] = []
        params: list[Any] = []

        if ticker:
            conditions.append("TICKER = %s")
            params.append(ticker.upper())
        if metric_category:
            conditions.append("METRIC_CATEGORY = %s")
            params.append(metric_category.lower())

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        sql = f"""
            SELECT TICKER, FILING_TYPE, FILING_DATE, METRIC_NAME,
                   METRIC_CATEGORY, VALUE, PERIOD, UNIT
            FROM SECSIGNAL.RAW.EXTRACTED_FINANCIALS
            {where}
            ORDER BY METRIC_CATEGORY, METRIC_NAME, FILING_DATE
            LIMIT %s
        """
        cursor.execute(sql, params)
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        if not rows:
            logger.debug("generate_chart_data_empty", ticker=ticker)
            return []

        # Group by metric_category to produce one chart per category
        charts = _group_into_charts(rows, ticker)
        logger.debug("generate_chart_data", ticker=ticker, charts=len(charts))
        return charts

    except Exception:
        logger.exception("generate_chart_data_failed", ticker=ticker)
        return []
    finally:
        cursor.close()


def generate_trend_charts(
    ticker: str | None = None,
) -> list[dict[str, Any]]:
    """Generate time-series charts from risk factor word counts.

    Queries fct_risk_factors for word count and delta over filing dates,
    producing line-chart-ready data for Streamlit.

    Args:
        ticker: Filter by ticker. None for all.

    Returns:
        List of chart dicts with chart_type='line', data=[{label, value}].
    """
    conn = get_snowflake_connection()
    cursor = conn.cursor()
    try:
        conditions: list[str] = []
        params: list[Any] = []

        if ticker:
            conditions.append("TICKER = %s")
            params.append(ticker.upper())

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        sql = f"""
            SELECT TICKER, FILING_TYPE, FILING_DATE, WORD_COUNT,
                   WORD_COUNT_DELTA
            FROM SECSIGNAL.MARTS.FCT_RISK_FACTORS
            {where}
            ORDER BY TICKER, FILING_DATE
        """
        cursor.execute(sql, params)
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        if not rows:
            logger.debug("generate_trend_charts_empty", ticker=ticker)
            return []

        charts = _build_trend_charts(rows, ticker)
        logger.debug("generate_trend_charts", ticker=ticker, charts=len(charts))
        return charts

    except Exception:
        logger.exception("generate_trend_charts_failed", ticker=ticker)
        return []
    finally:
        cursor.close()


def _build_trend_charts(
    rows: list[dict[str, Any]], ticker: str | None
) -> list[dict[str, Any]]:
    """Build line chart structures from risk factor time-series rows."""
    from collections import defaultdict

    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_ticker[r.get("TICKER", "?")].append(r)

    charts = []
    for tk, tk_rows in by_ticker.items():
        if len(tk_rows) < 2:
            continue

        # Word count over time
        wc_data = []
        for r in tk_rows:
            date_str = str(r.get("FILING_DATE", ""))
            ftype = r.get("FILING_TYPE", "")
            wc_data.append({
                "label": f"{date_str} ({ftype})",
                "value": float(r.get("WORD_COUNT", 0)),
            })

        charts.append({
            "chart_type": "line",
            "title": f"{tk} — Risk Factor Word Count Over Time",
            "category": "risk_trend",
            "unit": "words",
            "ticker": tk,
            "data": wc_data,
        })

        # Word count delta over time
        delta_data = []
        for r in tk_rows:
            date_str = str(r.get("FILING_DATE", ""))
            ftype = r.get("FILING_TYPE", "")
            delta_data.append({
                "label": f"{date_str} ({ftype})",
                "value": float(r.get("WORD_COUNT_DELTA", 0)),
            })

        charts.append({
            "chart_type": "line",
            "title": f"{tk} — Risk Factor Change (Delta) Over Time",
            "category": "risk_delta_trend",
            "unit": "words",
            "ticker": tk,
            "data": delta_data,
        })

    return charts


def generate_comparison_chart(
    tickers: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Generate grouped bar chart comparing risk factor word counts across tickers.

    Args:
        tickers: List of tickers to compare. None for all.

    Returns:
        List with one chart dict containing per-ticker data points.
    """
    conn = get_snowflake_connection()
    cursor = conn.cursor()
    try:
        if tickers:
            placeholders = ", ".join(["%s"] * len(tickers))
            where = f"WHERE TICKER IN ({placeholders})"
            params = [t.upper() for t in tickers]
        else:
            where = ""
            params = []

        sql = f"""
            SELECT TICKER, FILING_TYPE, FILING_DATE, WORD_COUNT,
                   WORD_COUNT_DELTA
            FROM SECSIGNAL.MARTS.FCT_RISK_FACTORS
            {where}
            ORDER BY TICKER, FILING_DATE DESC
        """
        cursor.execute(sql, params)
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        if not rows:
            logger.debug("generate_comparison_chart_empty")
            return []

        # Take latest filing per ticker
        seen: set[str] = set()
        data_points = []
        for r in rows:
            tk = r.get("TICKER", "?")
            if tk in seen:
                continue
            seen.add(tk)
            data_points.append({
                "label": f"{tk} ({r.get('FILING_TYPE', '')} {str(r.get('FILING_DATE', ''))[:10]})",
                "value": float(r.get("WORD_COUNT", 0)),
                "ticker": tk,
            })

        if len(data_points) < 2:
            return []

        ticker_label = ", ".join(sorted(seen))
        charts = [{
            "chart_type": "bar",
            "title": f"Risk Factor Length Comparison — {ticker_label}",
            "category": "risk_comparison",
            "unit": "words",
            "ticker": "COMPARISON",
            "data": data_points,
        }]

        logger.debug("generate_comparison_chart", tickers=list(seen), charts=len(charts))
        return charts

    except Exception:
        logger.exception("generate_comparison_chart_failed")
        return []
    finally:
        cursor.close()


def _group_into_charts(
    rows: list[dict[str, Any]], ticker: str | None
) -> list[dict[str, Any]]:
    """Group flat metric rows into chart structures."""
    from collections import defaultdict

    by_category: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        cat = r.get("METRIC_CATEGORY", "other")
        by_category[cat].append(r)

    charts = []
    for category, cat_rows in by_category.items():
        if category in ("growth", "other"):
            # Growth metrics work well as bar charts
            chart_type = "bar"
        elif category == "margin":
            chart_type = "bar"
        else:
            # revenue, income, expense, etc. — bar chart for comparison
            chart_type = "bar"

        # Build data points: each row is a data point
        data_points = []
        for r in cat_rows:
            label = r.get("METRIC_NAME", "Unknown")
            period = r.get("PERIOD", "")
            if period:
                label = f"{label} ({period})"
            data_points.append({
                "label": label,
                "value": float(r.get("VALUE", 0)),
                "unit": r.get("UNIT", ""),
                "ticker": r.get("TICKER", ""),
                "period": period,
                "metric_name": r.get("METRIC_NAME", ""),
            })

        ticker_label = ticker.upper() if ticker else "All Companies"
        title = f"{ticker_label} — {category.replace('_', ' ').title()} Metrics"

        # Determine unit for axis label
        units = {dp["unit"] for dp in data_points if dp["unit"]}
        unit_label = units.pop() if len(units) == 1 else "mixed"

        charts.append({
            "chart_type": chart_type,
            "title": title,
            "category": category,
            "unit": unit_label,
            "ticker": ticker or "ALL",
            "data": data_points,
        })

    return charts


# ---------------------------------------------------------------------------
# --- Advanced chart generators (removable: advanced-viz) ---
# ---------------------------------------------------------------------------

# Color palette for Python-side series generation
CHART_COLORS_PYTHON = [
    "#5eadad", "#3B82F6", "#10B981", "#8B5CF6",
    "#EF4444", "#06B6D4", "#F59E0B", "#EC4899",
]


def generate_composed_revenue_margin(
    ticker: str,
) -> list[dict[str, Any]]:
    """Composed bar+line chart: Revenue (bars) vs Margin % (line).

    Use case: Analysts want to see absolute revenue alongside profitability
    trend in a single chart — the classic combo chart.
    """
    conn = get_snowflake_connection()
    cursor = conn.cursor()
    try:
        sql = """
            SELECT METRIC_NAME, METRIC_CATEGORY, VALUE, PERIOD, UNIT
            FROM SECSIGNAL.RAW.EXTRACTED_FINANCIALS
            WHERE TICKER = %s
              AND METRIC_CATEGORY IN ('revenue', 'margin')
            ORDER BY METRIC_CATEGORY, METRIC_NAME
        """
        cursor.execute(sql, [ticker.upper()])
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        if not rows:
            return []

        revenue_rows = [r for r in rows if r["METRIC_CATEGORY"] == "revenue"]
        margin_rows = [r for r in rows if r["METRIC_CATEGORY"] == "margin"]

        if not revenue_rows or not margin_rows:
            return []

        # Build combined dataset keyed by metric name
        margin_lookup = {r["METRIC_NAME"]: float(r["VALUE"]) for r in margin_rows}
        data = []
        for r in revenue_rows:
            label = r["METRIC_NAME"]
            period = r.get("PERIOD", "")
            if period:
                label = f"{label} ({period})"
            data.append({
                "label": label,
                "revenue": float(r["VALUE"]),
                "margin": margin_lookup.get(r["METRIC_NAME"], 0),
            })

        if not data:
            return []

        return [{
            "chart_type": "composed",
            "title": f"{ticker.upper()} — Revenue vs Margin",
            "category": "revenue_margin",
            "unit": "USD / %",
            "ticker": ticker.upper(),
            "data": data,
            "width_hint": "full",
            "series": [
                {"key": "revenue", "name": "Revenue", "color": "#3B82F6"},
                {"key": "margin", "name": "Margin %", "color": "#F59E0B"},
            ],
        }]

    except Exception:
        logger.exception("generate_composed_revenue_margin_failed", ticker=ticker)
        return []
    finally:
        cursor.close()


def generate_area_trend(
    ticker: str,
) -> list[dict[str, Any]]:
    """Area chart for risk factor word count trend.

    Use case: Shows the magnitude of risk disclosure growth over time
    with filled area for visual emphasis.
    """
    conn = get_snowflake_connection()
    cursor = conn.cursor()
    try:
        sql = """
            SELECT FILING_DATE, FILING_TYPE, WORD_COUNT
            FROM SECSIGNAL.MARTS.FCT_RISK_FACTORS
            WHERE TICKER = %s
            ORDER BY FILING_DATE
        """
        cursor.execute(sql, [ticker.upper()])
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        if len(rows) < 2:
            return []

        data = []
        for r in rows:
            date_str = str(r.get("FILING_DATE", ""))[:10]
            ftype = r.get("FILING_TYPE", "")
            data.append({
                "label": f"{date_str} ({ftype})",
                "value": float(r.get("WORD_COUNT", 0)),
            })

        # Reference line at average word count
        avg_wc = sum(d["value"] for d in data) / len(data)

        return [{
            "chart_type": "area",
            "title": f"{ticker.upper()} — Risk Disclosure Volume Trend",
            "category": "risk_area",
            "unit": "words",
            "ticker": ticker.upper(),
            "data": data,
            "reference_lines": [
                {"value": round(avg_wc), "label": "Avg", "color": "#F59E0B"},
            ],
        }]

    except Exception:
        logger.exception("generate_area_trend_failed", ticker=ticker)
        return []
    finally:
        cursor.close()


def generate_expense_pie(
    ticker: str,
) -> list[dict[str, Any]]:
    """Pie chart showing expense breakdown by metric.

    Use case: Proportional view of where money is spent — R&D vs SGA vs COGS etc.
    """
    conn = get_snowflake_connection()
    cursor = conn.cursor()
    try:
        sql = """
            SELECT METRIC_NAME, VALUE
            FROM SECSIGNAL.RAW.EXTRACTED_FINANCIALS
            WHERE TICKER = %s AND METRIC_CATEGORY = 'expense'
            ORDER BY VALUE DESC
        """
        cursor.execute(sql, [ticker.upper()])
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        if len(rows) < 2:
            return []

        data = []
        for r in rows:
            val = abs(float(r.get("VALUE", 0)))
            if val > 0:
                data.append({
                    "label": r["METRIC_NAME"],
                    "value": val,
                })

        if len(data) < 2:
            return []

        # --- Limit pie slices to top 6, bucket rest into "Other" (removable: advanced-viz) ---
        MAX_PIE_SLICES = 6
        if len(data) > MAX_PIE_SLICES:
            data.sort(key=lambda d: d["value"], reverse=True)
            top = data[:MAX_PIE_SLICES - 1]
            other_val = sum(d["value"] for d in data[MAX_PIE_SLICES - 1:])
            top.append({"label": "Other", "value": other_val})
            data = top
        # --- End pie slice limit ---

        return [{
            "chart_type": "pie",
            "title": f"{ticker.upper()} — Expense Breakdown",
            "category": "expense_pie",
            "unit": "USD",
            "ticker": ticker.upper(),
            "data": data,
        }]

    except Exception:
        logger.exception("generate_expense_pie_failed", ticker=ticker)
        return []
    finally:
        cursor.close()


def generate_financial_radar(
    ticker: str,
) -> list[dict[str, Any]]:
    """Radar chart for multi-dimensional financial health profile.

    Use case: Quick visual fingerprint — compares revenue, income, margin,
    growth, etc. on a single radial chart. Normalized to 0–100 scale.
    """
    conn = get_snowflake_connection()
    cursor = conn.cursor()
    try:
        sql = """
            SELECT METRIC_CATEGORY, AVG(VALUE) AS AVG_VALUE
            FROM SECSIGNAL.RAW.EXTRACTED_FINANCIALS
            WHERE TICKER = %s
            GROUP BY METRIC_CATEGORY
            ORDER BY METRIC_CATEGORY
        """
        cursor.execute(sql, [ticker.upper()])
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        if len(rows) < 3:
            return []

        # Normalize to 0-100 scale
        values = [abs(float(r.get("AVG_VALUE", 0))) for r in rows]
        max_val = max(values) if values else 1

        data = []
        for r, v in zip(rows, values):
            normalized = round((v / max_val) * 100, 1) if max_val > 0 else 0
            data.append({
                "label": r["METRIC_CATEGORY"].replace("_", " ").title(),
                "value": normalized,
            })

        return [{
            "chart_type": "radar",
            "title": f"{ticker.upper()} — Financial Health Profile",
            "category": "financial_radar",
            "unit": "score (0-100)",
            "ticker": ticker.upper(),
            "data": data,
        }]

    except Exception:
        logger.exception("generate_financial_radar_failed", ticker=ticker)
        return []
    finally:
        cursor.close()


def generate_income_waterfall(
    ticker: str,
) -> list[dict[str, Any]]:
    """Waterfall chart for income statement flow.

    Use case: Shows how revenue flows through costs/expenses to net income —
    classic investment banking income statement waterfall.
    Positive values add, negative values subtract.
    """
    conn = get_snowflake_connection()
    cursor = conn.cursor()
    try:
        sql = """
            SELECT METRIC_NAME, METRIC_CATEGORY, VALUE
            FROM SECSIGNAL.RAW.EXTRACTED_FINANCIALS
            WHERE TICKER = %s
              AND METRIC_CATEGORY IN ('revenue', 'expense', 'income')
            ORDER BY METRIC_CATEGORY, METRIC_NAME
        """
        cursor.execute(sql, [ticker.upper()])
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        if not rows:
            return []

        revenue = [r for r in rows if r["METRIC_CATEGORY"] == "revenue"]
        expense = [r for r in rows if r["METRIC_CATEGORY"] == "expense"]
        income = [r for r in rows if r["METRIC_CATEGORY"] == "income"]

        # Build waterfall steps
        data = []

        # Start with total revenue
        total_rev = sum(float(r["VALUE"]) for r in revenue)
        if total_rev > 0:
            data.append({"label": "Total Revenue", "value": round(total_rev)})

        # Subtract expenses (shown as negative contributions)
        for r in expense[:4]:  # Cap at 4 expense items for readability
            val = abs(float(r["VALUE"]))
            if val > 0:
                data.append({
                    "label": r["METRIC_NAME"],
                    "value": -round(val),
                })

        # Add net income as result
        net = sum(float(r["VALUE"]) for r in income)
        if income:
            data.append({"label": "Net Income", "value": round(net)})

        if len(data) < 3:
            return []

        return [{
            "chart_type": "waterfall",
            "title": f"{ticker.upper()} — Income Statement Waterfall",
            "category": "income_waterfall",
            "unit": "USD",
            "ticker": ticker.upper(),
            "data": data,
            "width_hint": "full",
        }]

    except Exception:
        logger.exception("generate_income_waterfall_failed", ticker=ticker)
        return []
    finally:
        cursor.close()


def generate_comparison_radar(
    tickers: list[str],
) -> list[dict[str, Any]]:
    """Multi-series radar chart comparing financial profiles across tickers.

    Use case: Side-by-side comparison of two or more companies on the same
    radar — shows relative strengths/weaknesses at a glance.
    """
    if not tickers or len(tickers) < 2:
        return []

    conn = get_snowflake_connection()
    cursor = conn.cursor()
    try:
        placeholders = ", ".join(["%s"] * len(tickers))
        sql = f"""
            SELECT TICKER, METRIC_CATEGORY, AVG(VALUE) AS AVG_VALUE
            FROM SECSIGNAL.RAW.EXTRACTED_FINANCIALS
            WHERE TICKER IN ({placeholders})
            GROUP BY TICKER, METRIC_CATEGORY
            ORDER BY METRIC_CATEGORY, TICKER
        """
        cursor.execute(sql, [t.upper() for t in tickers])
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        if not rows:
            return []

        from collections import defaultdict
        by_cat: dict[str, dict[str, float]] = defaultdict(dict)
        for r in rows:
            cat = r["METRIC_CATEGORY"]
            tk = r["TICKER"]
            by_cat[cat][tk] = abs(float(r.get("AVG_VALUE", 0)))

        if len(by_cat) < 3:
            return []

        # Normalize each category to 0–100
        categories = sorted(by_cat.keys())
        all_tickers = sorted({t.upper() for t in tickers})

        data = []
        for cat in categories:
            vals = by_cat[cat]
            max_v = max(vals.values()) if vals else 1
            point: dict[str, Any] = {
                "label": cat.replace("_", " ").title(),
            }
            for tk in all_tickers:
                raw = vals.get(tk, 0)
                point[tk] = round((raw / max_v) * 100, 1) if max_v > 0 else 0
            data.append(point)

        colors = CHART_COLORS_PYTHON[:len(all_tickers)]
        series = [
            {"key": tk, "name": tk, "color": colors[i]}
            for i, tk in enumerate(all_tickers)
        ]

        return [{
            "chart_type": "radar",
            "title": f"Financial Profile Comparison — {', '.join(all_tickers)}",
            "category": "comparison_radar",
            "unit": "score (0-100)",
            "ticker": "COMPARISON",
            "data": data,
            "series": series,
            "width_hint": "full",
        }]

    except Exception:
        logger.exception("generate_comparison_radar_failed", tickers=tickers)
        return []
    finally:
        cursor.close()


def generate_risk_comparison_composed(
    tickers: list[str],
) -> list[dict[str, Any]]:
    """Composed chart: Word Count (bars) + Delta % (line) across tickers.

    Use case: Compare absolute risk disclosure size with rate of change
    across multiple companies in one view.
    """
    if not tickers or len(tickers) < 2:
        return []

    conn = get_snowflake_connection()
    cursor = conn.cursor()
    try:
        placeholders = ", ".join(["%s"] * len(tickers))
        sql = f"""
            SELECT TICKER, FILING_DATE, WORD_COUNT, WORD_COUNT_DELTA
            FROM SECSIGNAL.MARTS.FCT_RISK_FACTORS
            WHERE TICKER IN ({placeholders})
            ORDER BY TICKER, FILING_DATE DESC
        """
        cursor.execute(sql, [t.upper() for t in tickers])
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        if not rows:
            return []

        # Take latest filing per ticker
        seen: set[str] = set()
        data = []
        for r in rows:
            tk = r.get("TICKER", "?")
            if tk in seen:
                continue
            seen.add(tk)
            wc = float(r.get("WORD_COUNT", 0))
            delta = float(r.get("WORD_COUNT_DELTA", 0))
            prev_wc = wc - delta
            delta_pct = round((delta / prev_wc) * 100, 1) if prev_wc != 0 else 0
            data.append({
                "label": tk,
                "word_count": round(wc),
                "delta_pct": delta_pct,
            })

        if len(data) < 2:
            return []

        return [{
            "chart_type": "composed",
            "title": "Risk Disclosure: Volume vs Change Rate",
            "category": "risk_composed",
            "unit": "words / %",
            "ticker": "COMPARISON",
            "data": data,
            "width_hint": "full",
            "series": [
                {"key": "word_count", "name": "Word Count", "color": "#3B82F6"},
                {"key": "delta_pct", "name": "Change %", "color": "#EF4444"},
            ],
        }]

    except Exception:
        logger.exception("generate_risk_comparison_composed_failed")
        return []
    finally:
        cursor.close()


# --- End advanced chart generators ---
