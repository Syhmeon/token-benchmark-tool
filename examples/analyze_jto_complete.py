#!/usr/bin/env python3
"""
JTO Complete Analysis - CEX + DEX Combined

This script demonstrates the full methodology for determining
benchmark FDV using both CEX and DEX data sources.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))
sys.path.insert(0, str(parent_dir / "src"))

import json
from datetime import datetime, timezone
import ccxt

# Import directly from file to avoid package issues
exec(open(parent_dir / "src" / "providers" / "dex" / "flipside_provider.py").read())


def fetch_cex_data():
    """Fetch CEX price data for JTO."""
    cex_data = {}

    # Bybit - First exchange at 16:00 UTC
    try:
        bybit = ccxt.bybit({'enableRateLimit': True})
        bybit.load_markets()

        since = datetime(2023, 12, 7, 16, 0, 0, tzinfo=timezone.utc)
        since_ms = int(since.timestamp() * 1000)

        candles = bybit.fetch_ohlcv('JTO/USDT', '1m', since=since_ms, limit=60)

        if candles:
            first = candles[0]
            hl_ratio = first[2] / first[3] if first[3] > 0 else 999

            cex_data['bybit'] = {
                'first_candle_time': '2023-12-07 16:00:00 UTC',
                'open': first[1],
                'high': first[2],
                'low': first[3],
                'close': first[4],
                'hl_ratio': round(hl_ratio, 1),
                'is_tge_candle': hl_ratio > 5,
                'flag': 'SUSPECT - extreme wicks' if max(c[2] for c in candles[:15]) > 6 else 'OK',
                'vwap_1h': calculate_vwap(candles),
                'median_close_1h': calculate_median_close(candles),
            }
    except Exception as e:
        cex_data['bybit'] = {'error': str(e)}

    # Binance - 16:30 UTC (30min delay)
    try:
        binance = ccxt.binance({'enableRateLimit': True})
        binance.load_markets()

        since = datetime(2023, 12, 7, 16, 30, 0, tzinfo=timezone.utc)
        since_ms = int(since.timestamp() * 1000)

        candles = binance.fetch_ohlcv('JTO/USDT', '1m', since=since_ms, limit=60)

        if candles:
            first = candles[0]
            hl_ratio = first[2] / first[3] if first[3] > 0 else 999

            cex_data['binance'] = {
                'first_candle_time': '2023-12-07 16:30:00 UTC',
                'open': first[1],
                'high': first[2],
                'low': first[3],
                'close': first[4],
                'hl_ratio': round(hl_ratio, 1),
                'is_tge_candle': hl_ratio > 5,
                'flag': '30min delay from TGE',
                'vwap_1h': calculate_vwap(candles),
                'median_close_1h': calculate_median_close(candles),
            }
    except Exception as e:
        cex_data['binance'] = {'error': str(e)}

    return cex_data


def calculate_vwap(candles):
    """Calculate Volume Weighted Average Price."""
    typical_prices = [(c[2] + c[3] + c[4]) / 3 for c in candles]
    volumes = [c[5] for c in candles]

    vwap_num = sum(tp * v for tp, v in zip(typical_prices, volumes))
    vwap_denom = sum(volumes)

    return round(vwap_num / vwap_denom, 4) if vwap_denom > 0 else 0


def calculate_median_close(candles):
    """Calculate median close price."""
    closes = sorted([c[4] for c in candles])
    n = len(closes)
    if n % 2 == 0:
        return round((closes[n//2 - 1] + closes[n//2]) / 2, 4)
    return round(closes[n//2], 4)


def main():
    print("=" * 70)
    print("JTO COMPLETE ANALYSIS - CEX + DEX COMBINED")
    print("=" * 70)

    # 1. Token Info
    token_info = {
        "name": "Jito",
        "symbol": "JTO",
        "blockchain": "Solana",
        "coingecko_id": "jito-governance-token",
        "category": ["Liquid Staking", "MEV Infrastructure", "DeFi"],
        "listing_date": "2023-12-07",
        "total_supply": 1_000_000_000,
        "tge_circulating_pct": 11.5,
    }

    print(f"\nToken: {token_info['name']} ({token_info['symbol']})")
    print(f"   Blockchain: {token_info['blockchain']}")
    print(f"   Category: {', '.join(token_info['category'])}")
    print(f"   Listing Date: {token_info['listing_date']}")

    # 2. Fetch CEX Data
    print("\n" + "=" * 70)
    print("CEX DATA (via CCXT)")
    print("=" * 70)

    cex_data = fetch_cex_data()

    for exchange, data in cex_data.items():
        print(f"\n{exchange.upper()}:")
        if 'error' in data:
            print(f"  Error: {data['error']}")
        else:
            print(f"  First candle: {data['first_candle_time']}")
            print(f"  OPEN: ${data['open']:.4f}")
            print(f"  HIGH: ${data['high']:.4f}")
            print(f"  CLOSE: ${data['close']:.4f}")
            print(f"  H/L Ratio: {data['hl_ratio']}x {'[TGE CANDLE]' if data['is_tge_candle'] else ''}")
            print(f"  Flag: {data['flag']}")
            print(f"  VWAP 1h: ${data['vwap_1h']:.4f}")
            print(f"  Median Close 1h: ${data['median_close_1h']:.4f}")

    # 3. DEX Data
    print("\n" + "=" * 70)
    print("DEX DATA (via Flipside)")
    print("=" * 70)

    dex_result = get_jto_stabilization()

    print(f"\nFirst DEX swap: {JTO_DEX_DATA['first_swap']}")
    print(f"Stabilization hour: {dex_result.stabilization_hour.strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"Reference price: ${dex_result.reference_price:.4f}")
    print(f"Spread: {dex_result.spread_pct:.2f}%")
    print(f"Confidence: {dex_result.confidence}")
    print(f"Total swaps: {dex_result.total_swaps:,}")

    print("\nDEX prices at stabilization:")
    for dex, price in dex_result.dex_prices.items():
        print(f"  {dex}: ${price:.4f}")

    # 4. Price Comparison
    print("\n" + "=" * 70)
    print("PRICE COMPARISON - ALL SOURCES")
    print("=" * 70)

    price_sources = []

    # CEX prices
    if 'bybit' in cex_data and 'error' not in cex_data['bybit']:
        price_sources.append({
            'source': 'Bybit OPEN',
            'price': cex_data['bybit']['open'],
            'reliability': 'LOW',
            'note': 'Test trade'
        })
        price_sources.append({
            'source': 'Bybit VWAP 1h',
            'price': cex_data['bybit']['vwap_1h'],
            'reliability': 'MEDIUM',
            'note': 'Includes suspicious wicks'
        })

    if 'binance' in cex_data and 'error' not in cex_data['binance']:
        price_sources.append({
            'source': 'Binance OPEN',
            'price': cex_data['binance']['open'],
            'reliability': 'LOW',
            'note': '30min delay + test trade'
        })
        price_sources.append({
            'source': 'Binance VWAP 1h',
            'price': cex_data['binance']['vwap_1h'],
            'reliability': 'MEDIUM',
            'note': '30min delay'
        })

    # DEX price
    price_sources.append({
        'source': 'DEX Stabilization',
        'price': dex_result.reference_price,
        'reliability': 'HIGH',
        'note': f'5 DEX converge, spread {dex_result.spread_pct:.2f}%'
    })

    print(f"\n{'Source':<25} {'Price':<12} {'Reliability':<12} {'Note'}")
    print("-" * 70)
    for ps in price_sources:
        fdv = token_info['total_supply'] * ps['price'] / 1e9
        print(f"{ps['source']:<25} ${ps['price']:<11.4f} {ps['reliability']:<12} {ps['note']}")

    # 5. Benchmark FDV
    print("\n" + "=" * 70)
    print("BENCHMARK VALUATION (RECOMMENDED)")
    print("=" * 70)

    benchmark = calculate_benchmark_fdv(
        reference_price=dex_result.reference_price,
        total_supply=token_info['total_supply'],
        tge_circulating_pct=token_info['tge_circulating_pct']
    )

    print(f"\nMethod: DEX Stabilization (+2h after TGE)")
    print(f"Reference Price: ${benchmark['reference_price']:.4f}")
    print(f"FDV: ${benchmark['fdv_usd']:,.0f} ({benchmark['fdv_usd']/1e9:.2f}B)")
    print(f"MCap (TGE): ${benchmark['mcap_usd']:,.0f} ({benchmark['mcap_usd']/1e6:.1f}M)")
    print(f"Confidence: {dex_result.confidence}")

    # 6. Fundraising Comparison
    fundraising = {
        'total_raised': 12_100_000,
        'rounds': [
            {'name': 'Seed', 'date': '2021-12', 'amount': 2_100_000},
            {'name': 'Series A', 'date': '2022-08', 'amount': 10_000_000},
        ]
    }

    fdv_to_raised = benchmark['fdv_usd'] / fundraising['total_raised']

    print("\n" + "=" * 70)
    print("FUNDRAISING COMPARISON")
    print("=" * 70)
    print(f"\nTotal Raised: ${fundraising['total_raised']:,}")
    print(f"FDV at Launch: ${benchmark['fdv_usd']:,}")
    print(f"FDV/Raised Ratio: {fdv_to_raised:.1f}x")

    # 7. Save Report
    report = {
        "token": token_info,
        "cex_data": cex_data,
        "dex_data": {
            "source": "flipside",
            "first_swap": JTO_DEX_DATA["first_swap"],
            "stabilization_hour": dex_result.stabilization_hour.isoformat(),
            "reference_price": dex_result.reference_price,
            "spread_pct": dex_result.spread_pct,
            "confidence": dex_result.confidence,
            "dex_prices": dex_result.dex_prices,
            "total_swaps": dex_result.total_swaps,
        },
        "benchmark_valuation": {
            "method": "dex_stabilization",
            "reference_price": benchmark["reference_price"],
            "fdv_usd": benchmark["fdv_usd"],
            "mcap_usd": benchmark["mcap_usd"],
            "confidence": dex_result.confidence,
        },
        "fundraising": {
            **fundraising,
            "fdv_to_raised_ratio": round(fdv_to_raised, 1),
        },
        "methodology_notes": [
            "CEX first candles show H/L ratio > 30x - flagged as TGE candles",
            "Bybit shows impossible wicks ($32) vs ATH ($5.91) - marked SUSPECT",
            "DEX stabilization at +2h when 5 protocols converge within 0.41% spread",
            "Benchmark price = volume-weighted average of DEX prices at stabilization",
        ],
    }

    output_path = Path(__file__).parent / "output" / "jto_complete_analysis.json"
    output_path.parent.mkdir(exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\nReport saved to: {output_path}")


if __name__ == "__main__":
    main()
