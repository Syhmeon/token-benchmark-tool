#!/usr/bin/env python3
"""
Token analysis with proper rate limiting.
"""

import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from src.resolution.token_resolver import TokenResolver
from src.providers.price.ccxt_provider import CCXTPriceProvider
from src.providers.price.coingecko_price import CoinGeckoPriceProvider
from src.providers.supply.coingecko_supply import CoinGeckoSupplyProvider
from src.calculator.price_selector import PriceSelector
from src.calculator.valuation import ValuationCalculator
from src.core.exceptions import TokenNotFoundError

# Token list with known CoinGecko IDs
TOKENS = [
    {"name": "Jito", "cg_id": "jito-governance-token", "symbol": "JTO",
     "tge_date": "2023-12-07", "tge_circ_pct": 11.5},  # 115M / 1B
    {"name": "EigenLayer", "cg_id": "eigenlayer", "symbol": "EIGEN",
     "tge_date": "2024-10-01", "tge_circ_pct": 6.05},  # ~114M / 1.67B at TGE
    {"name": "Marlin", "cg_id": "marlin", "symbol": "POND",
     "tge_date": "2020-09-01", "tge_circ_pct": 15.0},
    {"name": "Manifold Finance", "cg_id": "manifold-finance", "symbol": "FOLD",
     "tge_date": "2021-04-01", "tge_circ_pct": 10.0},
    {"name": "Paladin", "cg_id": "paladin", "symbol": "PAL",
     "tge_date": "2021-10-01", "tge_circ_pct": 5.0},
]

# Not yet listed tokens
NOT_LISTED = [
    {"name": "Rakurai", "symbol": "RAI", "status": "Not listed yet"},
    {"name": "DoubleZero", "symbol": "2Z", "status": "Not listed yet"},
    {"name": "Solayer", "symbol": "LAYER", "status": "Recently announced - may not be on CoinGecko"},
    {"name": "bloXroute", "symbol": "BLXR", "status": "No token launched"},
    {"name": "Semantic Layer", "symbol": "42", "status": "Not found on CoinGecko"},
]

def analyze_token(cg_id: str, symbol: str, tge_circ_pct: float = None):
    """Analyze a single token with explicit delays."""
    resolver = TokenResolver(rate_limit_calls=5, rate_limit_period=60)
    ccxt_provider = CCXTPriceProvider(
        exchanges=["binance", "okx", "bybit", "kucoin", "gateio"],
        rate_limit_calls=10,
        rate_limit_period=60
    )
    supply_provider = CoinGeckoSupplyProvider(rate_limit_calls=5, rate_limit_period=60)
    cg_price_provider = CoinGeckoPriceProvider(rate_limit_calls=5, rate_limit_period=60)
    price_selector = PriceSelector()
    calc = ValuationCalculator()

    result = {}

    # 1. Resolve token
    print(f"  Resolving {cg_id}...")
    try:
        token_info = resolver.resolve(cg_id)
        result["coingecko_id"] = token_info.coingecko_id
        result["name"] = token_info.name
        result["symbol"] = token_info.symbol
        result["categories"] = token_info.categories[:3] if token_info.categories else []
    except Exception as e:
        return {"error": str(e)}

    time.sleep(3)  # Rate limit pause

    # 2. Get supply
    print(f"  Fetching supply...")
    try:
        supply = supply_provider.get_supply(token_info.coingecko_id)
        result["total_supply"] = supply.total_supply
        result["max_supply"] = supply.max_supply
        result["circulating_now"] = supply.circulating_supply_current

        # Estimate TGE circulating
        if tge_circ_pct and supply.total_supply:
            tge_circ = supply.total_supply * (tge_circ_pct / 100)
            result["tge_circulating_est"] = tge_circ
    except Exception as e:
        result["supply_error"] = str(e)

    time.sleep(3)

    # 3. Get exchange prices
    print(f"  Fetching exchange prices...")
    try:
        listings = ccxt_provider.get_listings_all_exchanges(symbol)
        valid_listings = [l for l in listings if l.has_data]
        result["exchanges_with_data"] = len(valid_listings)

        if valid_listings:
            ref_price = price_selector.select(valid_listings)
            if ref_price:
                result["initial_price"] = ref_price.price_usd
                result["initial_exchange"] = ref_price.source_exchange
                result["initial_pair"] = ref_price.source_pair
                result["initial_timestamp"] = ref_price.timestamp.isoformat()

                # Calculate FDV
                if supply.total_supply:
                    result["initial_fdv"] = supply.total_supply * ref_price.price_usd

                # Calculate MCap if we have TGE circulating estimate
                if result.get("tge_circulating_est"):
                    result["initial_mcap_est"] = result["tge_circulating_est"] * ref_price.price_usd
    except Exception as e:
        result["price_error"] = str(e)

    time.sleep(2)

    # 4. Try CoinGecko historical as fallback
    if "initial_price" not in result:
        print(f"  Trying CoinGecko historical...")
        try:
            cg_listing = cg_price_provider.get_listing_data(token_info.coingecko_id)
            if cg_listing and cg_listing.first_candle:
                result["initial_price"] = cg_listing.first_candle.open
                result["initial_exchange"] = "coingecko"
                result["initial_timestamp"] = cg_listing.first_candle.timestamp.isoformat()
                result["price_source"] = "coingecko_historical"

                if supply.total_supply:
                    result["initial_fdv"] = supply.total_supply * cg_listing.first_candle.open
        except Exception as e:
            result["cg_price_error"] = str(e)

    return result


def main():
    print("=" * 80)
    print("TOKEN LISTING FDV ANALYSIS")
    print("=" * 80)

    results = []

    # Analyze listed tokens
    for token in TOKENS:
        print(f"\n{'='*60}")
        print(f"ANALYZING: {token['name']} ({token['symbol']})")
        print(f"{'='*60}")

        result = analyze_token(
            token["cg_id"],
            token["symbol"],
            token.get("tge_circ_pct")
        )
        result["token_name"] = token["name"]
        result["symbol_expected"] = token["symbol"]
        results.append(result)

        # Print result
        if "error" in result:
            print(f"  ERROR: {result['error']}")
        else:
            print(f"\n  Results for {token['name']}:")
            print(f"  - CoinGecko ID: {result.get('coingecko_id')}")
            print(f"  - Total Supply: {result.get('total_supply', 'N/A'):,.0f}" if result.get('total_supply') else "  - Total Supply: N/A")
            print(f"  - Initial Price: ${result.get('initial_price', 0):.6f}" if result.get('initial_price') else "  - Initial Price: N/A")
            print(f"  - Initial FDV: ${result.get('initial_fdv', 0):,.0f}" if result.get('initial_fdv') else "  - Initial FDV: N/A")
            print(f"  - Initial MCap (est): ${result.get('initial_mcap_est', 0):,.0f}" if result.get('initial_mcap_est') else "  - Initial MCap: N/A (need TGE circ)")
            print(f"  - Exchange: {result.get('initial_exchange', 'N/A')}")
            print(f"  - Timestamp: {result.get('initial_timestamp', 'N/A')}")

        # Pause between tokens to respect rate limits
        print("\n  Waiting 10s before next token...")
        time.sleep(10)

    # Report not-listed tokens
    print(f"\n{'='*60}")
    print("TOKENS NOT YET LISTED / NOT FOUND")
    print(f"{'='*60}")
    for token in NOT_LISTED:
        print(f"  - {token['name']} ({token['symbol']}): {token['status']}")
        results.append({
            "token_name": token["name"],
            "symbol_expected": token["symbol"],
            "status": token["status"],
            "listed": False
        })

    # Summary table
    print(f"\n{'='*80}")
    print("SUMMARY TABLE")
    print(f"{'='*80}")
    print(f"{'Token':<20} {'Symbol':<8} {'Initial Price':<15} {'Initial FDV':<20} {'Exchange':<12}")
    print("-" * 80)

    for r in results:
        name = r.get("token_name", "?")[:19]
        symbol = r.get("symbol_expected", "?")[:7]
        if r.get("listed") == False:
            print(f"{name:<20} {symbol:<8} {'NOT LISTED':<15} {'-':<20} {'-':<12}")
        elif r.get("error"):
            print(f"{name:<20} {symbol:<8} {'ERROR':<15} {'-':<20} {'-':<12}")
        else:
            price = f"${r.get('initial_price', 0):.4f}" if r.get('initial_price') else "N/A"
            fdv = f"${r.get('initial_fdv', 0):,.0f}" if r.get('initial_fdv') else "N/A"
            exch = r.get('initial_exchange', 'N/A')[:11]
            print(f"{name:<20} {symbol:<8} {price:<15} {fdv:<20} {exch:<12}")

    # Save results
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)

    with open(output_dir / "token_analysis_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\nResults saved to: {output_dir / 'token_analysis_results.json'}")


if __name__ == "__main__":
    main()
