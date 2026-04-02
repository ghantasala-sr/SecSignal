"""SecSignal Evaluation CLI — run the evaluation suite and persist results.

Usage:
    cd /path/to/SecSignal
    .venv/bin/python scripts/run_evaluation.py                  # full suite
    .venv/bin/python scripts/run_evaluation.py --category trend # subset
    .venv/bin/python scripts/run_evaluation.py --compare        # compare last 2 runs
    .venv/bin/python scripts/run_evaluation.py --no-persist     # skip Snowflake persistence
    .venv/bin/python scripts/run_evaluation.py --list           # list test cases
"""

from __future__ import annotations

import argparse
import os
import sys

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Load .env if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def main() -> None:
    parser = argparse.ArgumentParser(description="SecSignal Evaluation Suite")
    parser.add_argument(
        "--category",
        choices=["trend", "comparison", "anomaly", "followup"],
        default=None,
        help="Run only test cases in this category",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare the last two evaluation runs",
    )
    parser.add_argument(
        "--no-persist",
        action="store_true",
        help="Skip persisting results to Snowflake",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_cases",
        help="List all test cases and exit",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-case output, only show summary",
    )
    args = parser.parse_args()

    # List mode
    if args.list_cases:
        from secsignal.evaluation.test_cases import get_test_cases
        cases = get_test_cases(args.category)
        print(f"\n  {'ID':<12} {'Category':<12} {'Expected Type':<15} {'Query'}")
        print(f"  {'-'*12} {'-'*12} {'-'*15} {'-'*40}")
        for tc in cases:
            print(f"  {tc.id:<12} {tc.category:<12} {tc.expected_query_type:<15} {tc.query[:55]}")
        print(f"\n  Total: {len(cases)} test cases\n")
        return

    # Compare mode
    if args.compare:
        from secsignal.evaluation.runner import compare_runs
        compare_runs()
        return

    # Verify Snowflake credentials
    required_vars = ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PASSWORD"]
    missing = [v for v in required_vars if not os.environ.get(v)]
    if missing:
        print(f"ERROR: Missing environment variables: {', '.join(missing)}")
        print("Set them in .env or export them before running.")
        sys.exit(1)

    # Run evaluation
    from secsignal.evaluation.runner import run_evaluation
    result = run_evaluation(
        category=args.category,
        persist=not args.no_persist,
        verbose=not args.quiet,
    )

    # Exit code: 0 if overall >= 3.0, 1 otherwise
    overall = result.get("avg_overall", 0)
    if overall < 3.0:
        print(f"  WARNING: Overall score {overall:.2f} is below threshold (3.0)")
        sys.exit(1)


if __name__ == "__main__":
    main()
