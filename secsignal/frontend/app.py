"""SecSignal Streamlit frontend — interactive SEC filing intelligence UI.

Provides:
- Company ticker multi-select
- Query type toggle (trend / comparison / anomaly / auto)
- Natural language query input
- Response display with cited text + inline chart images
- Source citations sidebar
"""

from __future__ import annotations

import base64
import os
import sys

# Ensure the project root is on sys.path for imports
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Load .env BEFORE any Snowflake imports
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(_project_root, ".env"))

import streamlit as st  # noqa: E402
import pandas as pd  # noqa: E402
from secsignal.agents.graph import run_query  # noqa: E402

# --- Page config ---
st.set_page_config(
    page_title="SecSignal — SEC Filing Intelligence",
    page_icon="📊",
    layout="wide",
)

# --- Header ---
st.title("SecSignal")
st.caption("Agentic RAG for SEC Financial Intelligence")

# --- Sidebar: configuration ---
with st.sidebar:
    st.header("Configuration")

    tickers = st.multiselect(
        "Companies",
        options=["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA"],
        default=[],
        help="Select tickers to focus on, or leave empty for all",
    )

    query_type = st.radio(
        "Query Type",
        options=["auto", "trend", "comparison", "anomaly"],
        index=0,
        help="Auto lets the agent classify your query",
    )

    st.divider()
    st.header("About")
    st.markdown(
        "SecSignal analyzes SEC filings (10-K, 10-Q) using a multi-agent "
        "system powered by Snowflake Cortex. It can detect trends, compare "
        "companies, and flag anomalies in financial disclosures."
    )

# --- Main area: query input ---
query = st.text_area(
    "Ask a question about SEC filings",
    placeholder="e.g. How has Apple's risk factor disclosure changed over the last year?",
    height=100,
)

col1, col2 = st.columns([1, 5])
with col1:
    submit = st.button("Analyze", type="primary", use_container_width=True)

# --- Process query ---
if submit and query:
    with st.spinner("Analyzing SEC filings..."):
        try:
            result = run_query(
                query=query,
                tickers=tickers if tickers else None,
            )
        except Exception as e:
            st.error(f"Agent error: {e}")
            st.stop()

    # --- Display results ---
    st.divider()

    # Query classification info
    col_type, col_tickers = st.columns(2)
    with col_type:
        st.metric("Query Type", result.get("query_type", "general").title())
    with col_tickers:
        detected = result.get("tickers", [])
        st.metric("Tickers", ", ".join(detected) if detected else "All")

    # Main answer
    st.subheader("Analysis")
    st.markdown(result.get("final_answer", "No response generated."))

    # Anomalies section
    anomalies = result.get("anomaly_scores", [])
    if anomalies:
        st.subheader("Detected Anomalies")
        for a in anomalies:
            direction_icon = "+" if a.get("direction") == "increase" else "-"
            st.warning(
                f"**{a.get('ticker', '?')}** ({a.get('filing_date', '?')}): "
                f"{a.get('metric', '?')} = {a.get('value', 0):+,} "
                f"| z-score: {a.get('z_score', 0):+.2f} ({a.get('direction', '?')})"
            )

    # Charts section
    charts = result.get("retrieved_charts", [])
    if charts:
        st.subheader("Related Charts")
        # Check if all charts have warnings (likely logos)
        all_warned = all(c.get("_warning") for c in charts)
        if all_warned:
            st.info(
                "No financial charts were found in the filings for this query. "
                "The images below are likely logos or decorative elements extracted "
                "from filing documents."
            )
        chart_cols = st.columns(min(len(charts), 3))
        for i, chart in enumerate(charts):
            with chart_cols[i % 3]:
                b64 = chart.get("image_data_b64", "")
                if b64:
                    try:
                        img_bytes = base64.b64decode(b64)
                        caption = (
                            f"{chart.get('ticker', '?')} — "
                            f"{chart.get('description', 'Chart')[:80]}"
                        )
                        if chart.get("_warning"):
                            caption += " (may be logo)"
                        st.image(img_bytes, caption=caption)
                    except Exception:
                        st.info(f"Chart: {chart.get('description', 'No description')}")
                else:
                    st.info(f"Chart: {chart.get('description', 'No description')}")

    # Generated charts section (from extracted financial data)
    gen_charts = result.get("generated_charts", [])
    if gen_charts:
        st.subheader("Financial Charts")
        for gc in gen_charts:
            title = gc.get("title", "Chart")
            data_points = gc.get("data", [])
            unit_label = gc.get("unit", "")
            if not data_points:
                continue

            st.markdown(f"**{title}**")
            df = pd.DataFrame(data_points)

            if "label" in df.columns and "value" in df.columns:
                # Truncate long labels for readability
                df["label"] = df["label"].str[:60]
                chart_df = df.set_index("label")[["value"]]

                if unit_label in ("USD_millions", "USD_billions"):
                    chart_df.columns = [f"Value ({unit_label.replace('_', ' ')})"]
                elif unit_label == "percent":
                    chart_df.columns = ["Value (%)"]
                else:
                    chart_df.columns = ["Value"]

                st.bar_chart(chart_df)
            else:
                st.dataframe(df)

    # Sources sidebar
    sources = result.get("sources", [])
    if sources:
        with st.sidebar:
            st.divider()
            st.header("Sources")
            for s in sources:
                st.markdown(
                    f"- **{s.get('ticker', '?')}** | {s.get('filing_type', '?')} | "
                    f"{s.get('filing_date', '?')}"
                )

elif submit:
    st.warning("Please enter a query.")

# --- Sample queries ---
with st.expander("Sample queries"):
    st.markdown("""
- **Trend:** How has Apple's risk factor disclosure changed over the last year?
- **Comparison:** Compare AAPL and MSFT financial filing lengths
- **Anomaly:** Are there any unusual changes in risk factor disclosures across all companies?
- **Visual:** Show me charts from NVDA's latest filing
- **General:** What did Tesla disclose about supply chain risks?
""")
