"""
Unified CEX Historical Data Provider

Tries multiple sources in order of preference:
1. Binance Data Vision (FREE, best historical data)
2. Finnhub (FREE tier, 60 calls/min, fallback)
3. Returns error if no data found

Usage:
    from src.providers.price.cex_provider import CEXProvider

    provider = CEXProvider()
    candles, source, error = provider.get_tge_candles("JTO", "2023-12-07 16:00:00")
"""

import os
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import logging

from .binance_historical import BinanceHistoricalProvider
from .finnhub_provider import FinnhubProvider

logger = logging.getLogger(__name__)


class CEXProvider:
    """
    Unified CEX data provider with automatic fallback.

    Source Priority:
    1. Binance Data Vision - FREE, complete historical data since 2017
    2. Finnhub - FREE tier (requires API key), multi-exchange

    For DEX data, use Flipside MCP directly.
    """

    def __init__(self, finnhub_api_key: Optional[str] = None):
        """
        Initialize unified CEX provider.

        Args:
            finnhub_api_key: Optional Finnhub API key. Falls back to FINNHUB_API_KEY env var.
        """
        self.binance = BinanceHistoricalProvider()
        self.finnhub = FinnhubProvider(finnhub_api_key)

    def get_tge_candles(
        self,
        symbol: str,
        tge_date: str,  # "YYYY-MM-DD HH:MM:SS"
        num_candles: int = 10,
        quote: str = "USDT"
    ) -> Tuple[List[Dict], str, Optional[str]]:
        """
        Fetch TGE candles from the best available source.

        Args:
            symbol: Token symbol (e.g., "JTO")
            tge_date: TGE datetime string (UTC)
            num_candles: Number of candles to fetch
            quote: Quote currency

        Returns:
            Tuple of (candles, source_name, error_message)
            - candles: List of candle dicts with minute, time, open, high, low, close
            - source_name: "binance" or "finnhub" or "none"
            - error_message: None if success, error string if failed
        """
        tge_dt = datetime.strptime(tge_date, "%Y-%m-%d %H:%M:%S")

        # Try Binance first (FREE, best data)
        logger.info(f"Trying Binance Data Vision for {symbol}...")
        info = self.binance.get_listing_info(symbol, tge_dt, quote)

        if "error" not in info and info.get("first_10_candles"):
            candles = info["first_10_candles"][:num_candles]
            logger.info(f"Found {len(candles)} candles from Binance")
            return candles, "binance", None

        # Try Finnhub as fallback
        if self.finnhub.api_key:
            logger.info(f"Trying Finnhub for {symbol}...")
            candles, error = self.finnhub.get_tge_candles(symbol, tge_dt, num_candles, quote)

            if candles:
                logger.info(f"Found {len(candles)} candles from Finnhub")
                return candles, "finnhub", None

            if error:
                logger.warning(f"Finnhub error: {error}")
        else:
            logger.info("Finnhub skipped (no API key)")

        # No data found
        error_msg = f"No CEX data found for {symbol}. Try DEX data via Flipside."
        return [], "none", error_msg

    def get_full_listing_info(
        self,
        symbol: str,
        tge_date: str,
        quote: str = "USDT"
    ) -> Dict:
        """
        Get comprehensive listing info from best available source.

        Returns dict with:
        - source: "binance" | "finnhub" | "none"
        - first_trade_time
        - first_price
        - first_10_candles
        - first_hour_stats (if available)
        - error (if failed)
        """
        tge_dt = datetime.strptime(tge_date, "%Y-%m-%d %H:%M:%S")

        # Try Binance
        info = self.binance.get_listing_info(symbol, tge_dt, quote)

        if "error" not in info:
            info["source"] = "binance"
            return info

        # Try Finnhub
        if self.finnhub.api_key:
            candles, error = self.finnhub.get_tge_candles(symbol, tge_dt, 60, quote)

            if candles:
                first_candle = candles[0]
                return {
                    "source": "finnhub",
                    "pair": f"{symbol.upper()}{quote}",
                    "first_trade_time": f"{tge_date} UTC (approximate)",
                    "first_price": first_candle["open"],
                    "first_candle": first_candle,
                    "first_10_candles": candles[:10],
                    "first_hour_stats": {
                        "high": max(c["high"] for c in candles),
                        "low": min(c["low"] for c in candles),
                        "high_low_ratio": round(
                            max(c["high"] for c in candles) /
                            min(c["low"] for c in candles), 2
                        ) if min(c["low"] for c in candles) > 0 else None
                    }
                }

        return {
            "source": "none",
            "error": f"No CEX data for {symbol}. Use Flipside for DEX data."
        }


# CLI helper
def main():
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Fetch CEX historical data")
    parser.add_argument("symbol", help="Token symbol")
    parser.add_argument("date", help="TGE date (YYYY-MM-DD)")
    parser.add_argument("--time", default="00:00:00", help="TGE time (HH:MM:SS)")
    parser.add_argument("--finnhub-key", help="Finnhub API key")

    args = parser.parse_args()

    provider = CEXProvider(args.finnhub_key)

    tge_datetime = f"{args.date} {args.time}"
    info = provider.get_full_listing_info(args.symbol, tge_datetime)

    print(json.dumps(info, indent=2, default=str))


if __name__ == "__main__":
    main()
