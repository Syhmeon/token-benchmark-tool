#!/usr/bin/env python3
"""
CLI tool to fetch CEX historical data.

Sources (in priority order):
1. Binance Data Vision (FREE, complete historical data)
2. Finnhub (FREE tier with API key, multi-exchange)

Usage:
    python scripts/fetch_cex_data.py JTO 2023-12-07
    python scripts/fetch_cex_data.py EIGEN 2024-10-01 --time 05:00:00
    python scripts/fetch_cex_data.py LAYER 2025-02-11 --finnhub-key YOUR_KEY

Get free Finnhub API key at: https://finnhub.io/register
For tokens not found on CEX, use Flipside DEX data via MCP.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.providers.price.cex_provider import CEXProvider


def main():
    parser = argparse.ArgumentParser(
        description="Fetch CEX historical data (Binance + Finnhub fallback)"
    )
    parser.add_argument("symbol", help="Token symbol (e.g., JTO, EIGEN)")
    parser.add_argument("date", nargs="?", help="TGE date (YYYY-MM-DD)")
    parser.add_argument("--time", default="00:00:00", help="TGE time (HH:MM:SS)")
    parser.add_argument("--finnhub-key", help="Finnhub API key (or set FINNHUB_API_KEY env)")
    parser.add_argument("--candles", type=int, default=10, help="Number of candles")
    parser.add_argument("--output", "-o", help="Output JSON file")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")

    args = parser.parse_args()

    # Get Finnhub key from args or env
    finnhub_key = args.finnhub_key or os.environ.get("FINNHUB_API_KEY")

    provider = CEXProvider(finnhub_key)

    if not args.date:
        print("Error: date required")
        print("Usage: python scripts/fetch_cex_data.py SYMBOL YYYY-MM-DD --time HH:MM:SS")
        return 1

    try:
        tge_datetime = f"{args.date} {args.time}"
        datetime.strptime(tge_datetime, "%Y-%m-%d %H:%M:%S")  # Validate
    except ValueError:
        print("Error: Invalid date/time format. Use YYYY-MM-DD and HH:MM:SS")
        return 1

    print(f"Fetching {args.symbol} data for {tge_datetime} UTC...")
    print(f"Sources: Binance Data Vision" + (", Finnhub" if finnhub_key else " (Finnhub disabled - no API key)"))
    print()

    info = provider.get_full_listing_info(args.symbol, tge_datetime)

    # Raw JSON output
    if args.json:
        print(json.dumps(info, indent=2, default=str))
        return 0 if "error" not in info else 1

    # Check for error
    if "error" in info:
        print(f"Error: {info['error']}")
        print()
        print("Options:")
        print("  1. Add Finnhub API key: --finnhub-key YOUR_KEY")
        print("     Get free key at: https://finnhub.io/register")
        print("  2. Use Flipside DEX data via MCP for on-chain tokens")
        return 1

    # Pretty print
    source_name = info.get("source", "unknown").upper()
    print(f"{'='*60}")
    print(f"  {args.symbol}USDT - {source_name} Historical Data")
    print(f"{'='*60}")
    print(f"Source: {source_name}")
    print(f"First Trade: {info.get('first_trade_time', 'N/A')}")
    print(f"First Price: ${info.get('first_price', 0):.4f}")
    print()

    fc = info.get('first_candle', {})
    if fc:
        print("First Candle (TGE):")
        print(f"  Open:   ${fc.get('open', 0):.4f}")
        print(f"  High:   ${fc.get('high', 0):.4f}")
        print(f"  Low:    ${fc.get('low', 0):.4f}")
        print(f"  Close:  ${fc.get('close', 0):.4f}")
        if 'volume_usd' in fc:
            print(f"  Volume: ${fc['volume_usd']:,.0f}")
        if 'trades' in fc:
            print(f"  Trades: {fc['trades']:,}")
        print()

    fh = info.get('first_hour_stats', {})
    if fh:
        print("First Hour Stats:")
        if 'volume_usd' in fh:
            print(f"  Total Volume:    ${fh['volume_usd']:,.0f}")
        if 'total_trades' in fh:
            print(f"  Total Trades:    {fh['total_trades']:,}")
        if 'high_low_ratio' in fh:
            print(f"  High/Low Ratio:  {fh['high_low_ratio']}x")
        print()

    candles = info.get('first_10_candles', [])
    if candles:
        print(f"First {len(candles)} Candles:")
        print("-" * 60)
        print(f"{'Min':>4} {'Time':>10} {'Open':>10} {'High':>10} {'Low':>10} {'Close':>10}")
        print("-" * 60)
        for c in candles[:args.candles]:
            print(f"{c['minute']:>4} {c['time']:>10} ${c['open']:>9.4f} ${c['high']:>9.4f} ${c['low']:>9.4f} ${c['close']:>9.4f}")

    # Save to file if requested
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json.dumps(info, indent=2, default=str))
        print(f"\nSaved to: {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
