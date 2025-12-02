#!/usr/bin/env python3
"""
Example: Analyze Arbitrum (ARB) token listing.

This example demonstrates how to use the Token Listing Tool to analyze
Arbitrum's initial listing, including:
- Initial listing price across exchanges
- FDV and market cap at listing
- Token allocation breakdown
- Comparison with fundraising data

Run with:
    python examples/analyze_arb.py
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timezone

from src.orchestrator import TokenListingOrchestrator
from src.output.formatters import TableFormatter, JSONFormatter
from src.output.audit_trail import AuditTrailFormatter


def main():
    print("=" * 60)
    print("Token Listing Analysis: Arbitrum (ARB)")
    print("=" * 60)
    print()

    # Initialize orchestrator
    orchestrator = TokenListingOrchestrator()

    # ARB was listed on March 23, 2023
    # At TGE, ~1.275B tokens were circulating (12.75% of total supply)
    # Total supply: 10B tokens

    print("Analyzing ARB...")
    print("  - Listing date hint: 2023-03-23")
    print("  - Manual circulating supply: 1,275,000,000 (12.75% at TGE)")
    print()

    result = orchestrator.analyze(
        token_identifier="arbitrum",
        listing_date_hint=datetime(2023, 3, 23, tzinfo=timezone.utc),
        manual_circulating_supply=1_275_000_000,  # 12.75% at TGE
    )

    # Display results
    table_formatter = TableFormatter()
    print(table_formatter.format(result))

    # Show audit trail
    print("\n")
    audit_formatter = AuditTrailFormatter()
    print(audit_formatter.format_summary(result))

    # Save JSON output
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)

    json_formatter = JSONFormatter(indent=2)
    json_path = output_dir / "arb_analysis.json"
    json_formatter.format_to_file(result, str(json_path))
    print(f"\nJSON saved to: {json_path}")


if __name__ == "__main__":
    main()
