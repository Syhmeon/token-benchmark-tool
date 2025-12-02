#!/usr/bin/env python3
"""
Example: Analyze Optimism (OP) token listing.

This example demonstrates analyzing Optimism's TGE data.

OP Token Details:
- Listed: May 31, 2022
- Total Supply: 4,294,967,296 (2^32)
- At TGE: ~5% circulating (~214M tokens)

Run with:
    python examples/analyze_op.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timezone

from src.orchestrator import TokenListingOrchestrator
from src.output.formatters import TableFormatter


def main():
    print("=" * 60)
    print("Token Listing Analysis: Optimism (OP)")
    print("=" * 60)
    print()

    orchestrator = TokenListingOrchestrator()

    # OP was listed on May 31, 2022
    # Initial circulating: ~5% = 214,748,365 tokens

    print("Analyzing OP...")

    result = orchestrator.analyze(
        token_identifier="optimism",
        listing_date_hint=datetime(2022, 5, 31, tzinfo=timezone.utc),
        manual_circulating_supply=214_748_365,  # ~5% at TGE
    )

    # Display results
    formatter = TableFormatter()
    print(formatter.format(result))

    # Show key metrics
    print("\n" + "=" * 60)
    print("KEY METRICS SUMMARY")
    print("=" * 60)

    if result.valuation:
        v = result.valuation
        print(f"Initial Price:    ${v.initial_price_usd:.4f}")
        if v.initial_fdv:
            print(f"Initial FDV:      ${v.initial_fdv:,.0f}")
        if v.initial_market_cap:
            print(f"Initial MCap:     ${v.initial_market_cap:,.0f}")
        if v.fdv_to_raised_ratio:
            print(f"FDV/Raised:       {v.fdv_to_raised_ratio:.1f}x")

    if result.allocations:
        print(f"\nAllocations Total: {result.allocations.total_percentage:.1f}%")
        print(f"Complete:          {result.allocations.is_complete}")


if __name__ == "__main__":
    main()
