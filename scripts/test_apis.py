#!/usr/bin/env python3
"""Test script to verify API connections.

Usage:
    python scripts/test_apis.py
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
    print(f"  - CoinMarketCap: {'YES' if config.has_coinmarketcap() else 'NO'}")
    print(f"  - CryptoRank:    {'YES' if config.has_cryptorank() else 'NO'}")
    print(f"  - Messari:       {'YES' if config.has_messari() else 'NO'}")
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


def test_coinmarketcap(config):
    """Test CoinMarketCap API."""
    print("\n" + "=" * 60)
    print("COINMARKETCAP API TEST")
    print("=" * 60)

    if not config.has_coinmarketcap():
        print("  [SKIP] No API key configured")
        return None

    try:
        from src.providers.price.coinmarketcap_provider import CoinMarketCapProvider

        provider = CoinMarketCapProvider()

        if not provider.is_available():
            print("  [WARN] CoinMarketCap API not available")
            return False

        print("  [OK] CoinMarketCap API available")

        # Test quote
        quote = provider.get_quote("JTO")
        if quote:
            print(f"  [OK] JTO price: ${quote.price_usd:.4f}")
            print(f"  [OK] JTO market cap: ${quote.market_cap:,.0f}")
            print(f"  [OK] JTO FDV: ${quote.fully_diluted_market_cap:,.0f}")
            print(f"  [OK] CMC rank: #{quote.cmc_rank}")
        else:
            print("  [WARN] Could not fetch JTO quote")
            return False

        # Test info
        info = provider.get_info("JTO")
        if info:
            print(f"  [OK] Tags: {', '.join(info.tags[:3])}...")
            return True
        else:
            print("  [WARN] Could not fetch JTO info")
            return False

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

        # Note: Sandbox plan may not include fundraising data
        fundraising = provider.get_fundraising(symbol="JTO")

        if fundraising and fundraising.rounds:
            print(f"  [OK] JTO rounds: {len(fundraising.rounds)}")
            print(f"  [OK] Total raised: ${fundraising.total_raised_usd:,.0f}")
            return True
        else:
            print("  [INFO] No fundraising data (Sandbox plan may be limited)")
            return True  # API works, just limited data

    except Exception as e:
        print(f"  [ERROR] {e}")
        return False


def main():
    """Run all API tests."""
    print("\n" + "=" * 60)
    print("TOKEN BENCHMARK TOOL - API TEST")
    print("=" * 60)

    # Check for flags
    test_all = "--all" in sys.argv

    # Load config
    config = test_config()

    results = {}

    # Always test these (no API key needed)
    results["CoinGecko"] = test_coingecko()
    results["CCXT"] = test_ccxt()

    # Test CMC if configured
    if config.has_coinmarketcap():
        results["CoinMarketCap"] = test_coinmarketcap(config)

    # Test CryptoRank if --all or configured
    if test_all or config.has_cryptorank():
        results["CryptoRank"] = test_cryptorank(config)

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
