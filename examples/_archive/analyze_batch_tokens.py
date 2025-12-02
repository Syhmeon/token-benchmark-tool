#!/usr/bin/env python3
"""
Batch analysis for multiple tokens.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from datetime import datetime, timezone

from src.orchestrator import TokenListingOrchestrator
from src.output.formatters import TableFormatter, JSONFormatter, CSVFormatter
from src.core.exceptions import TokenNotFoundError, DataSourceError

# Tokens to analyze from the list
TOKENS = [
    {"name": "Jito", "id": "jito-governance-token", "symbol": "JTO"},
    {"name": "Paladin", "id": "paladin", "symbol": "PAL"},
    {"name": "Rakurai", "id": "rakurai", "symbol": "RAI"},  # May not be listed
    {"name": "DoubleZero", "id": "doublezero", "symbol": "2Z"},  # May not be listed
    {"name": "Solayer", "id": "solayer", "symbol": "LAYER"},  # May not be listed
    {"name": "EigenLayer", "id": "eigenlayer", "symbol": "EIGEN"},
    {"name": "bloXroute", "id": "bloxroute", "symbol": "BLXR"},  # May not be listed
    {"name": "Manifold Finance", "id": "manifold-finance", "symbol": "FOLD"},
    {"name": "Semantic Layer", "id": "semantic-layer", "symbol": "42"},  # May not be listed
    {"name": "Marlin", "id": "marlin", "symbol": "POND"},
]

def main():
    orchestrator = TokenListingOrchestrator()
    formatter = TableFormatter(use_rich=False)
    json_formatter = JSONFormatter(indent=2)

    results = []

    for token_info in TOKENS:
        print("\n" + "=" * 70)
        print(f"ANALYZING: {token_info['name']} ({token_info['symbol']})")
        print("=" * 70)

        # Try by ID first, then by symbol
        identifiers_to_try = [token_info["id"], token_info["symbol"].lower(), token_info["name"].lower()]

        result = None
        for identifier in identifiers_to_try:
            try:
                result = orchestrator.analyze(token_identifier=identifier)
                break
            except TokenNotFoundError:
                continue
            except DataSourceError as e:
                print(f"  Data source error for {identifier}: {e}")
                continue
            except Exception as e:
                print(f"  Error for {identifier}: {type(e).__name__}: {e}")
                continue

        if result:
            print(formatter.format(result))
            results.append({
                "token": token_info["name"],
                "symbol": token_info["symbol"],
                "status": "success",
                "coingecko_id": result.token.coingecko_id,
                "initial_price": result.reference_price.price_usd if result.reference_price else None,
                "initial_fdv": result.valuation.initial_fdv if result.valuation else None,
                "total_raised": result.valuation.total_raised_usd if result.valuation else None,
                "fdv_raised_ratio": result.valuation.fdv_to_raised_ratio if result.valuation else None,
            })
        else:
            print(f"  TOKEN NOT FOUND: {token_info['name']} ({token_info['symbol']})")
            print(f"  This token may not be listed on CoinGecko yet.")
            results.append({
                "token": token_info["name"],
                "symbol": token_info["symbol"],
                "status": "not_found",
            })

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    print(f"\n{'Token':<20} {'Symbol':<8} {'Status':<12} {'Initial FDV':<18} {'Raised':<15} {'FDV/Raised':<10}")
    print("-" * 90)

    for r in results:
        if r["status"] == "success":
            fdv = f"${r['initial_fdv']:,.0f}" if r.get("initial_fdv") else "N/A"
            raised = f"${r['total_raised']:,.0f}" if r.get("total_raised") else "N/A"
            ratio = f"{r['fdv_raised_ratio']:.1f}x" if r.get("fdv_raised_ratio") else "N/A"
            print(f"{r['token']:<20} {r['symbol']:<8} {'OK':<12} {fdv:<18} {raised:<15} {ratio:<10}")
        else:
            print(f"{r['token']:<20} {r['symbol']:<8} {'NOT FOUND':<12} {'-':<18} {'-':<15} {'-':<10}")

    # Save results
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)

    with open(output_dir / "batch_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\nResults saved to: {output_dir / 'batch_results.json'}")

if __name__ == "__main__":
    main()
