#!/usr/bin/env python3
"""
Token listing analysis using 1-MINUTE candles.

This script fetches the FIRST candle's OPEN price as the initial listing price.
We also detect TGE (Token Generation Event) candles with extreme volatility
(High/Low ratio > 5x) and flag them, but still use the OPEN price.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import ccxt
import time
import json
from datetime import datetime, timezone
from dataclasses import dataclass

# Configuration for tokens
TOKENS_CONFIG = {
    "JTO": {
        "name": "Jito",
        "coingecko_id": "jito-governance-token",
        "listing_date": datetime(2023, 12, 7, 16, 0, 0, tzinfo=timezone.utc),  # 16:00 UTC
        "exchanges": ["bybit", "bitget", "binance"],  # Try multiple exchanges
        "total_supply": 1_000_000_000,
        "tge_circulating_pct": 11.5,  # 115M / 1B
    },
    "EIGEN": {
        "name": "EigenLayer",
        "coingecko_id": "eigenlayer",
        "listing_date": datetime(2024, 10, 1, 4, 0, 0, tzinfo=timezone.utc),
        "exchanges": ["binance", "bybit", "okx"],
        "total_supply": 1_770_084_115,
        "tge_circulating_pct": 6.05,
    },
    "LAYER": {
        "name": "Solayer",
        "coingecko_id": "solayer",
        "listing_date": datetime(2025, 1, 15, 0, 0, 0, tzinfo=timezone.utc),  # Approximate
        "exchanges": ["binance", "bybit", "okx", "gateio"],
        "total_supply": 1_000_000_000,
        "tge_circulating_pct": 12.0,
    },
    "2Z": {
        "name": "DoubleZero",
        "coingecko_id": "doublezero",
        "listing_date": datetime(2025, 1, 20, 0, 0, 0, tzinfo=timezone.utc),  # Approximate
        "exchanges": ["binance", "bybit", "okx"],
        "total_supply": 1_000_000_000,
        "tge_circulating_pct": 10.0,
    },
    "POND": {
        "name": "Marlin",
        "coingecko_id": "marlin",
        "listing_date": datetime(2020, 9, 1, 0, 0, 0, tzinfo=timezone.utc),
        "exchanges": ["binance", "kucoin"],
        "total_supply": 10_000_000_000,
        "tge_circulating_pct": 15.0,
    },
}

TGE_VOLATILITY_THRESHOLD = 5.0  # H/L ratio to detect TGE candles


@dataclass
class ListingResult:
    symbol: str
    name: str
    exchange: str
    pair: str
    timestamp: datetime

    # Raw candle data
    first_candle_open: float
    first_candle_high: float
    first_candle_low: float
    first_candle_close: float
    first_candle_volume: float

    second_candle_open: float | None

    # Analysis
    is_tge_candle: bool
    volatility_ratio: float

    # Final price selection
    selected_price: float
    price_method: str

    # Calculated metrics
    initial_fdv: float | None
    initial_mcap: float | None


def get_exchange(exchange_id: str):
    """Initialize exchange."""
    try:
        exchange_class = getattr(ccxt, exchange_id)
        return exchange_class({'enableRateLimit': True, 'timeout': 30000})
    except Exception as e:
        print(f"  Error initializing {exchange_id}: {e}")
        return None


def fetch_first_candles(exchange, symbol: str, since: datetime, timeframe: str = "1m", limit: int = 5):
    """Fetch first N candles from listing time."""
    try:
        since_ms = int(since.timestamp() * 1000)
        candles = exchange.fetch_ohlcv(symbol, timeframe, since=since_ms, limit=limit)
        return candles
    except Exception as e:
        print(f"  Error fetching {symbol} from {exchange.id}: {e}")
        return None


def analyze_listing(symbol: str, config: dict) -> ListingResult | None:
    """Analyze listing for a token."""
    print(f"\n{'='*60}")
    print(f"ANALYZING: {config['name']} ({symbol})")
    print(f"{'='*60}")

    for exchange_id in config["exchanges"]:
        exchange = get_exchange(exchange_id)
        if not exchange:
            continue

        try:
            exchange.load_markets()
        except Exception as e:
            print(f"  Failed to load {exchange_id} markets: {e}")
            continue

        # Find pair
        pair = None
        for quote in ["USDT", "USDC", "USD"]:
            test_pair = f"{symbol}/{quote}"
            if test_pair in exchange.markets:
                pair = test_pair
                break

        if not pair:
            print(f"  {exchange_id}: No pair found for {symbol}")
            continue

        print(f"  {exchange_id}: Found {pair}")

        # Fetch 1-minute candles
        candles = fetch_first_candles(exchange, pair, config["listing_date"], "1m", 10)

        if not candles or len(candles) < 2:
            print(f"  {exchange_id}: No candle data available")
            continue

        first = candles[0]
        second = candles[1] if len(candles) > 1 else None

        ts = datetime.fromtimestamp(first[0] / 1000, tz=timezone.utc)
        o, h, l, c, v = first[1], first[2], first[3], first[4], first[5]

        # Calculate volatility
        volatility_ratio = h / l if l > 0 else 999
        is_tge = volatility_ratio > TGE_VOLATILITY_THRESHOLD

        print(f"  First candle: {ts.strftime('%Y-%m-%d %H:%M')} UTC")
        print(f"    O=${o:.4f} H=${h:.4f} L=${l:.4f} C=${c:.4f}")
        print(f"    H/L ratio: {volatility_ratio:.1f}x {'<-- TGE CANDLE' if is_tge else ''}")

        # Select price - ALWAYS use OPEN of first candle
        selected_price = o
        method = "first_candle_open"
        print(f"    Selected: OPEN = ${selected_price:.4f}")

        # Calculate metrics
        total_supply = config.get("total_supply", 0)
        tge_circ_pct = config.get("tge_circulating_pct", 0)

        initial_fdv = total_supply * selected_price if total_supply else None
        initial_mcap = (total_supply * tge_circ_pct / 100 * selected_price) if total_supply and tge_circ_pct else None

        print(f"\n  RESULTS:")
        print(f"    Initial Price: ${selected_price:.4f}")
        print(f"    Initial FDV:   ${initial_fdv:,.0f}" if initial_fdv else "    Initial FDV:   N/A")
        print(f"    Initial MCap:  ${initial_mcap:,.0f}" if initial_mcap else "    Initial MCap:  N/A")

        return ListingResult(
            symbol=symbol,
            name=config["name"],
            exchange=exchange_id,
            pair=pair,
            timestamp=ts,
            first_candle_open=o,
            first_candle_high=h,
            first_candle_low=l,
            first_candle_close=c,
            first_candle_volume=v,
            second_candle_open=second[1] if second else None,
            is_tge_candle=is_tge,
            volatility_ratio=volatility_ratio,
            selected_price=selected_price,
            price_method=method,
            initial_fdv=initial_fdv,
            initial_mcap=initial_mcap,
        )

    return None


def main():
    print("=" * 70)
    print("TOKEN LISTING ANALYSIS - CORRECTED VERSION")
    print("Using 1-minute candles with TGE detection")
    print("=" * 70)

    results = []

    # Analyze each token
    for symbol, config in TOKENS_CONFIG.items():
        try:
            result = analyze_listing(symbol, config)
            if result:
                results.append(result)
            else:
                results.append({"symbol": symbol, "name": config["name"], "status": "FAILED"})
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({"symbol": symbol, "name": config["name"], "status": "ERROR", "error": str(e)})

        time.sleep(2)  # Rate limiting

    # Summary table
    print("\n" + "=" * 90)
    print("SUMMARY TABLE")
    print("=" * 90)
    print(f"{'Token':<12} {'Exchange':<10} {'Time (UTC)':<18} {'Price':<12} {'FDV':<18} {'Method':<20}")
    print("-" * 90)

    for r in results:
        if isinstance(r, ListingResult):
            print(f"{r.symbol:<12} {r.exchange:<10} {r.timestamp.strftime('%Y-%m-%d %H:%M'):<18} "
                  f"${r.selected_price:<11.4f} ${r.initial_fdv:>16,.0f} {r.price_method:<20}")
        else:
            print(f"{r['symbol']:<12} {'-':<10} {'-':<18} {'-':<12} {'-':<18} {r.get('status', 'UNKNOWN'):<20}")

    # Save results
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)

    output_data = []
    for r in results:
        if isinstance(r, ListingResult):
            output_data.append({
                "symbol": r.symbol,
                "name": r.name,
                "exchange": r.exchange,
                "pair": r.pair,
                "timestamp": r.timestamp.isoformat(),
                "first_candle": {
                    "open": r.first_candle_open,
                    "high": r.first_candle_high,
                    "low": r.first_candle_low,
                    "close": r.first_candle_close,
                    "volume": r.first_candle_volume,
                },
                "second_candle_open": r.second_candle_open,
                "is_tge_candle": r.is_tge_candle,
                "volatility_ratio": r.volatility_ratio,
                "selected_price": r.selected_price,
                "price_method": r.price_method,
                "initial_fdv": r.initial_fdv,
                "initial_mcap": r.initial_mcap,
            })
        else:
            output_data.append(r)

    with open(output_dir / "listing_analysis_corrected.json", "w") as f:
        json.dump(output_data, f, indent=2, default=str)

    print(f"\nResults saved to: {output_dir / 'listing_analysis_corrected.json'}")


if __name__ == "__main__":
    main()
