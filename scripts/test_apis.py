#!/usr/bin/env python3
"""Test script to verify API connections.

Usage:
    python scripts/test_apis.py
    python scripts/test_apis.py --flipside-only
    python scripts/test_apis.py --all
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime
from src.core.config import get_config, reload_config


def test_config():
    """Test configuration loading."""
    print("\n" + "=" * 60)
    print("CONFIGURATION TEST")
    print("=" * 60)

    config = reload_config()
    sources = config.get_available_sources()

    print(f"\nAvailable sources: {', '.join(sources)}")
    print(f"\nAPI Keys configured:")
    print(f"  - Flipside:      {'YES' if config.has_flipside() else 'NO'}")
    print(f"  - CryptoRank:    {'YES' if config.has_cryptorank() else 'NO'}")
    print(f"  - DropsTab:      {'YES' if config.has_dropstab() else 'NO'}")
    print(f"  - CoinGecko:     {'YES (optional)' if config.has_coingecko() else 'NO (using public API)'}")

    return config


def test_coingecko():
    """Test CoinGecko API (always available)."""
    print("\n" + "=" * 60)
    print("COINGECKO API TEST")
    print("=" * 60)

    try:
        from src.providers.supply.coingecko_supply import CoinGeckoSupplyProvider

        provider = CoinGeckoSupplyProvider()

        if not provider.is_available():
            print("  [WARN] CoinGecko API not responding")
            return False

        print("  [OK] CoinGecko API available")

        # Test with JTO
        supply = provider.get_supply("jito-governance-token")
        if supply and supply.total_supply:
            print(f"  [OK] JTO total supply: {supply.total_supply:,.0f}")
            print(f"  [OK] JTO circulating: {supply.circulating_supply_current:,.0f}")
            return True
        else:
            print("  [WARN] Could not fetch JTO supply data")
            return False

    except Exception as e:
        print(f"  [ERROR] {e}")
        return False


def test_ccxt():
    """Test CCXT (always available)."""
    print("\n" + "=" * 60)
    print("CCXT API TEST")
    print("=" * 60)

    try:
        from src.providers.price.ccxt_provider import CCXTPriceProvider

        provider = CCXTPriceProvider(exchanges=["binance"])

        if not provider.is_available():
            print("  [WARN] CCXT not available")
            return False

        print("  [OK] CCXT available")

        # Test with JTO on Binance
        listing = provider.get_listing_for_exchange(
            exchange_id="binance",
            symbol="JTO",
            timeframe="1h",
            since_hint=datetime(2023, 12, 7),
        )

        if listing.has_data:
            print(f"  [OK] JTO first candle: {listing.first_candle.timestamp}")
            print(f"  [OK] Open: ${listing.first_candle.open:.4f}")
            return True
        else:
            print(f"  [WARN] {listing.error}")
            return False

    except Exception as e:
        print(f"  [ERROR] {e}")
        return False


def test_flipside(config):
    """Test Flipside SQL API."""
    print("\n" + "=" * 60)
    print("FLIPSIDE SQL API TEST")
    print("=" * 60)

    if not config.has_flipside():
        print("  [SKIP] No API key configured")
        return None

    try:
        from src.providers.dex.flipside_sql_provider import FlipsideSQLProvider

        provider = FlipsideSQLProvider()

        if not provider.is_available():
            print("  [WARN] Flipside API not available")
            return False

        print("  [OK] Flipside API key configured")
        print("  [INFO] Testing query (this may take 30-60 seconds)...")

        # Test with a simple query
        result = provider.find_stabilization_hour(
            token_mint="jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL",
            listing_date=datetime(2023, 12, 7),
            max_hours=6,
        )

        if result:
            print(f"  [OK] Stabilization hour: {result.stabilization_hour}")
            print(f"  [OK] Reference price: ${result.reference_price:.4f}")
            print(f"  [OK] DEX count: {len(result.dex_prices)}")
            return True
        else:
            print("  [WARN] No stabilization found (may be expected for test)")
            return True  # API works, just no data

    except Exception as e:
        print(f"  [ERROR] {e}")
        return False


def test_cryptorank(config):
    """Test CryptoRank API."""
    print("\n" + "=" * 60)
    print("CRYPTORANK API TEST")
    print("=" * 60)

    if not config.has_cryptorank():
        print("  [SKIP] No API key configured")
        return None

    try:
        from src.providers.fundraising.cryptorank import CryptoRankFundraisingProvider

        provider = CryptoRankFundraisingProvider(api_key=config.cryptorank_api_key)

        if not provider.is_available():
            print("  [WARN] CryptoRank API not available")
            return False

        print("  [OK] CryptoRank API available")

        # Test with JTO
        fundraising = provider.get_fundraising(symbol="jito")

        if fundraising and fundraising.rounds:
            print(f"  [OK] JTO rounds: {len(fundraising.rounds)}")
            print(f"  [OK] Total raised: ${fundraising.total_raised_usd:,.0f}")
            return True
        else:
            print("  [WARN] Could not fetch JTO fundraising data")
            return False

    except Exception as e:
        print(f"  [ERROR] {e}")
        return False


def test_dropstab(config):
    """Test DropsTab API."""
    print("\n" + "=" * 60)
    print("DROPSTAB API TEST")
    print("=" * 60)

    if not config.has_dropstab():
        print("  [SKIP] No API key configured")
        return None

    try:
        from src.providers.unlocks.dropstab_provider import DropsTabProvider

        provider = DropsTabProvider()

        if not provider.is_available():
            print("  [WARN] DropsTab API not available")
            return False

        print("  [OK] DropsTab API available")

        # Test with JTO
        unlocks = provider.get_unlock_schedule(symbol="JTO")

        if unlocks:
            print(f"  [OK] JTO total supply: {unlocks.total_supply:,.0f}")
            print(f"  [OK] Upcoming unlocks: {len(unlocks.upcoming_unlocks)}")
            return True
        else:
            print("  [WARN] Could not fetch JTO unlock data")
            return False

    except Exception as e:
        print(f"  [ERROR] {e}")
        return False


def main():
    """Run all API tests."""
    print("\n" + "=" * 60)
    print("TOKEN BENCHMARK TOOL - API TEST")
    print("=" * 60)

    # Check for flags
    flipside_only = "--flipside-only" in sys.argv
    test_all = "--all" in sys.argv

    # Load config
    config = test_config()

    results = {}

    # Always test these (no API key needed)
    if not flipside_only:
        results["CoinGecko"] = test_coingecko()
        results["CCXT"] = test_ccxt()

    # Test Flipside
    if flipside_only or test_all or config.has_flipside():
        results["Flipside"] = test_flipside(config)

    # Test others if --all or configured
    if test_all:
        results["CryptoRank"] = test_cryptorank(config)
        results["DropsTab"] = test_dropstab(config)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    for name, result in results.items():
        if result is True:
            status = "[OK]"
        elif result is False:
            status = "[FAIL]"
        else:
            status = "[SKIP]"
        print(f"  {status} {name}")

    # Return code
    failures = [r for r in results.values() if r is False]
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
