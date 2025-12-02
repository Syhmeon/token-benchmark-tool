#!/usr/bin/env python3
"""
Simple CLI for Token Benchmark Tool

Usage:
    python -m src.cli list                    # List all tokens in database
    python -m src.cli show <SYMBOL>           # Show benchmark for a token
    python -m src.cli check <SYMBOL>          # Check if token exists
    python -m src.cli summary                 # Show summary of all benchmarks
"""

import sys
import json
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analyzer import TokenAnalyzer


def main():
    if len(sys.argv) < 2:
        print_help()
        return

    command = sys.argv[1].lower()
    analyzer = TokenAnalyzer()

    if command == "list":
        tokens = analyzer.list_all()
        if tokens:
            print(f"Tokens in database ({len(tokens)}):")
            for t in tokens:
                print(f"  - {t}")
        else:
            print("No tokens in database yet.")

    elif command == "show":
        if len(sys.argv) < 3:
            print("Usage: python -m src.cli show <SYMBOL>")
            return
        symbol = sys.argv[2].upper()
        analyzer.display(symbol)

    elif command == "check":
        if len(sys.argv) < 3:
            print("Usage: python -m src.cli check <SYMBOL>")
            return
        symbol = sys.argv[2].upper()
        if analyzer.exists(symbol):
            print(f"[OK] {symbol} exists in database")
            benchmark = analyzer.get(symbol)
            print(f"  FDV: ${benchmark.fdv_usd:,.0f}")
            print(f"  Confidence: {benchmark.benchmark_confidence}")
        else:
            print(f"[--] {symbol} not found in database")

    elif command == "summary":
        summary = analyzer.store.get_summary()
        print("=" * 60)
        print("BENCHMARK DATABASE SUMMARY")
        print("=" * 60)
        print(f"Total tokens: {summary['count']}")
        if summary['count'] > 0:
            print(f"Total FDV: ${summary['total_fdv']:,.0f}")
            print()
            print(f"{'Token':<10} {'Blockchain':<12} {'FDV':<15} {'Confidence'}")
            print("-" * 60)
            for t in summary['tokens']:
                print(f"{t['symbol']:<10} {t['blockchain']:<12} ${t['fdv_usd']:,.0f}".ljust(37) + f" {t['confidence']}")

    elif command == "export":
        if len(sys.argv) < 3:
            print("Usage: python -m src.cli export <SYMBOL>")
            return
        symbol = sys.argv[2].upper()
        benchmark = analyzer.get(symbol)
        if benchmark:
            print(json.dumps(benchmark.to_dict(), indent=2))
        else:
            print(f"[ERROR] {symbol} not found")

    elif command == "help" or command == "-h" or command == "--help":
        print_help()

    else:
        print(f"Unknown command: {command}")
        print_help()


def print_help():
    print("""
Token Benchmark Tool - CLI

Commands:
  list              List all tokens in database
  show <SYMBOL>     Display benchmark details for a token
  check <SYMBOL>    Check if token exists in database
  summary           Show summary of all benchmarks
  export <SYMBOL>   Export benchmark as JSON
  help              Show this help message

Examples:
  python -m src.cli list
  python -m src.cli show JTO
  python -m src.cli check EIGEN
  python -m src.cli summary

Note: To add a new token, use the TokenAnalyzer class directly
or provide DEX data from FlipsideAI manually.
""")


if __name__ == "__main__":
    main()
