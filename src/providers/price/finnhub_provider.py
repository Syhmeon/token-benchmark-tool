"""
Finnhub Crypto Candles Provider

Free tier: 60 API calls/minute
Docs: https://finnhub.io/docs/api/crypto-candles

Use as fallback when Binance Data Vision doesn't have the token.
"""

import os
import time
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class FinnhubCandle:
    """Single OHLCV candle from Finnhub."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class FinnhubProvider:
    """
    Fetches crypto candles from Finnhub API.

    Free tier limits:
    - 60 API calls/minute
    - Limited historical depth (varies by exchange)

    Supported exchanges: BINANCE, COINBASE, KRAKEN, etc.
    Symbol format: EXCHANGE:SYMBOL (e.g., "BINANCE:BTCUSDT")
    """

    BASE_URL = "https://finnhub.io/api/v1"

    # Exchange prefixes for Finnhub
    EXCHANGES = ["BINANCE", "COINBASE", "KRAKEN", "BITFINEX", "GEMINI"]

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Finnhub provider.

        Args:
            api_key: Finnhub API key. If not provided, looks for FINNHUB_API_KEY env var.
        """
        self.api_key = api_key or os.environ.get("FINNHUB_API_KEY", "")
        if not self.api_key:
            logger.warning("No Finnhub API key provided. Set FINNHUB_API_KEY environment variable.")

        self.session = requests.Session()
        self._last_request_time = 0
        self._min_request_interval = 1.1  # Slightly over 1 second to stay under 60/min

    def _rate_limit(self):
        """Ensure we don't exceed rate limits."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.time()

    def get_candles(
        self,
        symbol: str,
        exchange: str,
        start_time: datetime,
        end_time: datetime,
        resolution: str = "1"  # 1 minute
    ) -> List[FinnhubCandle]:
        """
        Fetch candles from Finnhub.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            exchange: Exchange name (e.g., "BINANCE")
            start_time: Start datetime (UTC)
            end_time: End datetime (UTC)
            resolution: Candle resolution ("1", "5", "15", "30", "60", "D", "W", "M")

        Returns:
            List of FinnhubCandle objects
        """
        if not self.api_key:
            logger.error("No API key configured")
            return []

        finnhub_symbol = f"{exchange.upper()}:{symbol.upper()}"

        params = {
            "symbol": finnhub_symbol,
            "resolution": resolution,
            "from": int(start_time.timestamp()),
            "to": int(end_time.timestamp()),
            "token": self.api_key
        }

        self._rate_limit()

        try:
            response = self.session.get(
                f"{self.BASE_URL}/crypto/candle",
                params=params,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            if data.get("s") == "no_data":
                logger.warning(f"No data for {finnhub_symbol}")
                return []

            candles = []
            timestamps = data.get("t", [])
            opens = data.get("o", [])
            highs = data.get("h", [])
            lows = data.get("l", [])
            closes = data.get("c", [])
            volumes = data.get("v", [])

            for i in range(len(timestamps)):
                candle = FinnhubCandle(
                    timestamp=datetime.utcfromtimestamp(timestamps[i]),
                    open=opens[i],
                    high=highs[i],
                    low=lows[i],
                    close=closes[i],
                    volume=volumes[i] if i < len(volumes) else 0
                )
                candles.append(candle)

            return candles

        except requests.RequestException as e:
            logger.error(f"Finnhub API error: {e}")
            return []

    def get_tge_candles(
        self,
        symbol: str,
        tge_date: datetime,
        num_candles: int = 10,
        quote: str = "USDT"
    ) -> Tuple[List[Dict], Optional[str]]:
        """
        Fetch the first N 1-minute candles after TGE.

        Tries multiple exchanges until data is found.

        Args:
            symbol: Token symbol (e.g., "JTO")
            tge_date: TGE datetime (UTC)
            num_candles: Number of candles to fetch
            quote: Quote currency (default "USDT")

        Returns:
            Tuple of (candles_list, error_message)
        """
        pair = f"{symbol.upper()}{quote}"

        # Search window: TGE time + 1 hour
        end_time = tge_date + timedelta(hours=1)

        for exchange in self.EXCHANGES:
            candles = self.get_candles(pair, exchange, tge_date, end_time, "1")

            if candles:
                # Format for JSON output
                formatted = []
                for i, candle in enumerate(candles[:num_candles], 1):
                    formatted.append({
                        "minute": i,
                        "time": candle.timestamp.strftime("%H:%M:%S"),
                        "open": round(candle.open, 6),
                        "high": round(candle.high, 6),
                        "low": round(candle.low, 6),
                        "close": round(candle.close, 6)
                    })

                return formatted, None

        return [], f"No data found for {pair} on any exchange"

    def get_supported_symbols(self, exchange: str = "BINANCE") -> List[str]:
        """Get list of supported crypto symbols for an exchange."""
        if not self.api_key:
            return []

        self._rate_limit()

        try:
            response = self.session.get(
                f"{self.BASE_URL}/crypto/symbol",
                params={"exchange": exchange, "token": self.api_key},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            return [item.get("symbol", "") for item in data]

        except requests.RequestException as e:
            logger.error(f"Failed to get symbols: {e}")
            return []


def fetch_finnhub_tge_candles(
    symbol: str,
    tge_date: str,  # Format: "YYYY-MM-DD HH:MM:SS"
    api_key: Optional[str] = None,
    num_candles: int = 10
) -> Tuple[List[Dict], Optional[str]]:
    """
    Quick function to fetch TGE candles from Finnhub.

    Example:
        candles, error = fetch_finnhub_tge_candles("BTC", "2023-01-01 00:00:00", api_key="xxx")
    """
    provider = FinnhubProvider(api_key)
    tge_dt = datetime.strptime(tge_date, "%Y-%m-%d %H:%M:%S")
    return provider.get_tge_candles(symbol, tge_dt, num_candles)


if __name__ == "__main__":
    import json

    # Test with API key from environment
    api_key = os.environ.get("FINNHUB_API_KEY")

    if not api_key:
        print("Set FINNHUB_API_KEY environment variable to test")
        print("Get free API key at: https://finnhub.io/register")
    else:
        provider = FinnhubProvider(api_key)

        # Test BTC
        print("Testing BTC candles...")
        start = datetime(2024, 1, 1, 0, 0, 0)
        end = datetime(2024, 1, 1, 1, 0, 0)

        candles = provider.get_candles("BTCUSDT", "BINANCE", start, end, "1")
        print(f"Found {len(candles)} candles")

        if candles:
            print(json.dumps({
                "first": {
                    "time": candles[0].timestamp.isoformat(),
                    "open": candles[0].open,
                    "close": candles[0].close
                }
            }, indent=2))
