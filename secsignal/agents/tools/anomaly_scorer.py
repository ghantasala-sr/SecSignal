"""Anomaly scorer — rolling z-score detection over risk factor changes.

Computes z-scores over a rolling 8-quarter window on word count deltas
from fct_risk_factors. Flags metrics where |z| > 2.0 as anomalies.
"""

from __future__ import annotations

from typing import Any

import structlog

from secsignal.agents.connection import get_snowflake_connection

logger = structlog.get_logger(__name__)

Z_THRESHOLD = 2.0
ROLLING_WINDOW = 8  # quarters


def detect_anomalies(
    ticker: str | None = None,
    metric: str = "word_count_delta",
) -> list[dict[str, Any]]:
    """Detect anomalies in risk factor changes using rolling z-scores.

    Computes z-score = (value - rolling_avg) / rolling_stddev over an
    8-quarter window. Flags values where |z| > 2.0.

    Args:
        ticker: Filter by ticker. None scans all companies.
        metric: Metric to analyze. Currently supports 'word_count_delta'
                (change in risk factor word count between filings).

    Returns:
        List of anomaly dicts with ticker, filing_date, value, z_score,
        direction ('increase' or 'decrease').
    """
    conn = get_snowflake_connection()
    cursor = conn.cursor()
    try:
        ticker_filter = ""
        params: list[Any] = []
        if ticker:
            ticker_filter = "WHERE TICKER = %s"
            params.append(ticker.upper())

        # Use Snowflake window functions for rolling z-score computation
        sql = f"""
            WITH ranked AS (
                SELECT
                    TICKER,
                    COMPANY_NAME,
                    FILING_DATE,
                    FILING_TYPE,
                    WORD_COUNT,
                    WORD_COUNT_DELTA,
                    ROW_NUMBER() OVER (
                        PARTITION BY TICKER ORDER BY FILING_DATE
                    ) AS rn
                FROM SECSIGNAL.MARTS.FCT_RISK_FACTORS
                {ticker_filter}
            ),
            rolling_stats AS (
                SELECT
                    r.TICKER,
                    r.COMPANY_NAME,
                    r.FILING_DATE,
                    r.FILING_TYPE,
                    r.WORD_COUNT,
                    r.WORD_COUNT_DELTA,
                    AVG(r.WORD_COUNT_DELTA) OVER (
                        PARTITION BY r.TICKER
                        ORDER BY r.FILING_DATE
                        ROWS BETWEEN {ROLLING_WINDOW - 1} PRECEDING AND CURRENT ROW
                    ) AS rolling_avg,
                    STDDEV(r.WORD_COUNT_DELTA) OVER (
                        PARTITION BY r.TICKER
                        ORDER BY r.FILING_DATE
                        ROWS BETWEEN {ROLLING_WINDOW - 1} PRECEDING AND CURRENT ROW
                    ) AS rolling_stddev,
                    COUNT(*) OVER (
                        PARTITION BY r.TICKER
                        ORDER BY r.FILING_DATE
                        ROWS BETWEEN {ROLLING_WINDOW - 1} PRECEDING AND CURRENT ROW
                    ) AS window_size
                FROM ranked r
            )
            SELECT
                TICKER,
                COMPANY_NAME,
                FILING_DATE,
                FILING_TYPE,
                WORD_COUNT,
                WORD_COUNT_DELTA,
                rolling_avg,
                rolling_stddev,
                CASE
                    WHEN rolling_stddev > 0
                    THEN (WORD_COUNT_DELTA - rolling_avg) / rolling_stddev
                    ELSE 0
                END AS z_score
            FROM rolling_stats
            WHERE window_size >= 2
              AND rolling_stddev > 0
              AND ABS(
                  CASE
                      WHEN rolling_stddev > 0
                      THEN (WORD_COUNT_DELTA - rolling_avg) / rolling_stddev
                      ELSE 0
                  END
              ) > {Z_THRESHOLD}
            ORDER BY ABS(
                CASE
                    WHEN rolling_stddev > 0
                    THEN (WORD_COUNT_DELTA - rolling_avg) / rolling_stddev
                    ELSE 0
                END
            ) DESC
        """
        cursor.execute(sql, params)
        columns = [desc[0] for desc in cursor.description]
        raw_rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        # Format results
        anomalies = []
        for row in raw_rows:
            z = float(row["Z_SCORE"]) if row["Z_SCORE"] is not None else 0.0
            anomalies.append({
                "ticker": row["TICKER"],
                "company_name": row["COMPANY_NAME"],
                "filing_date": str(row["FILING_DATE"]),
                "filing_type": row["FILING_TYPE"],
                "metric": metric,
                "value": row["WORD_COUNT_DELTA"],
                "word_count": row["WORD_COUNT"],
                "z_score": round(z, 3),
                "direction": "increase" if z > 0 else "decrease",
                "rolling_avg": round(float(row["ROLLING_AVG"]), 1) if row["ROLLING_AVG"] else None,
                "rolling_stddev": round(float(row["ROLLING_STDDEV"]), 1) if row["ROLLING_STDDEV"] else None,
            })

        logger.debug("detect_anomalies", ticker=ticker, anomalies=len(anomalies))
        return anomalies

    except Exception:
        logger.exception("detect_anomalies_failed", ticker=ticker)
        return []
    finally:
        cursor.close()
