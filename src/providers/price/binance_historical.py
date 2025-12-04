"""
Binance Data Vision Historical Data Provider

Fetches historical 1-minute OHLCV data from Binance's free data archive.
URL: https://data.binance.vision/

This is the BEST source for historical CEX data because:
- FREE (no API key required)
- Complete historical data since 2017
- 1-minute granularity available
- Official Binance data
"""

import requests
import zipfile
import io
import csv
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class BinanceCandle:
    """Single OHLCV candle from Binance."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float
    trades: int


class BinanceHistoricalProvider:
    """
    Fetches historical klines from Binance Data Vision.

    Data is available as ZIP files containing CSV data.
    - Monthly files: https://data.binance.vision/data/spot/monthly/klines/{SYMBOL}/1m/
    - Daily files: https://data.binance.vision/data/spot/daily/klines/{SYMBOL}/1m/
    """

    BASE_URL = "https://data.binance.vision/data/spot"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'TokenBenchmarkTool/1.0'
        })

    def get_tge_candles(
        self,
        symbol: str,
        tge_date: datetime,
        num_candles: int = 10,
        quote: str = "USDT"
    ) -> Tuple[List[Dict], Optional[str]]:
        """
        Fetch the first N 1-minute candles after TGE.

        Args:
            symbol: Token symbol (e.g., "JTO", "EIGEN")
            tge_date: TGE datetime (UTC)
            num_candles: Number of candles to fetch (default 10)
            quote: Quote currency (default "USDT")

        Returns:
            Tuple of (candles_list, error_message)
            candles_list format: [{"minute": 1, "time": "HH:MM:SS", "open": x, "high": x, "low": x, "close": x}, ...]
        """
        pair = f"{symbol.upper()}{quote}"

        # Try daily file first (more precise), then monthly
        candles = self._fetch_daily_klines(pair, tge_date)

        if not candles:
            candles = self._fetch_monthly_klines(pair, tge_date)

        if not candles:
            return [], f"No data found for {pair} around {tge_date}"

        # Filter candles starting from TGE time
        tge_candles = [c for c in candles if c.timestamp >= tge_date]

        if not tge_candles:
            return [], f"No candles found after TGE time {tge_date}"

        # Take first N candles
        result_candles = tge_candles[:num_candles]

        # Format for JSON output
        formatted = []
        for i, candle in enumerate(result_candles, 1):
            formatted.append({
                "minute": i,
                "time": candle.timestamp.strftime("%H:%M:%S"),
                "open": round(candle.open, 6),
                "high": round(candle.high, 6),
                "low": round(candle.low, 6),
                "close": round(candle.close, 6)
            })

        return formatted, None

    def _fetch_daily_klines(self, pair: str, date: datetime) -> List[BinanceCandle]:
        """Fetch klines from daily ZIP file."""
        date_str = date.strftime("%Y-%m-%d")
        url = f"{self.BASE_URL}/daily/klines/{pair}/1m/{pair}-1m-{date_str}.zip"

        return self._download_and_parse(url)

    def _fetch_monthly_klines(self, pair: str, date: datetime) -> List[BinanceCandle]:
        """Fetch klines from monthly ZIP file."""
        month_str = date.strftime("%Y-%m")
        url = f"{self.BASE_URL}/monthly/klines/{pair}/1m/{pair}-1m-{month_str}.zip"

        return self._download_and_parse(url)

    def _download_and_parse(self, url: str) -> List[BinanceCandle]:
        """Download ZIP file and parse CSV contents."""
        try:
            logger.info(f"Fetching: {url}")
            response = self.session.get(url, timeout=30)

            if response.status_code == 404:
                logger.warning(f"File not found: {url}")
                return []

            response.raise_for_status()

            # Extract ZIP in memory
            with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                # Get the CSV file (should be only one)
                csv_name = zf.namelist()[0]
                with zf.open(csv_name) as f:
                    return self._parse_csv(f)

        except requests.RequestException as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return []
        except zipfile.BadZipFile as e:
            logger.error(f"Invalid ZIP file from {url}: {e}")
            return []

    def _parse_csv(self, file_obj) -> List[BinanceCandle]:
        """
        Parse Binance klines CSV.

        CSV columns:
        0: open_time (ms timestamp)
        1: open
        2: high
        3: low
        4: close
        5: volume
        6: close_time
        7: quote_volume
        8: trades
        9: taker_buy_base
        10: taker_buy_quote
        11: ignore
        """
        candles = []

        # Decode bytes to string and parse
        content = file_obj.read().decode('utf-8')
        reader = csv.reader(io.StringIO(content))

        for row in reader:
            if len(row) < 9:
                continue

            # Skip header rows or invalid timestamps
            try:
                open_time = int(row[0])
            except ValueError:
                # Skip header or non-numeric rows
                continue

            # Validate timestamp is reasonable (after 2017, before 2030)
            if open_time < 1483228800000 or open_time > 1893456000000:
                continue

            try:
                timestamp = datetime.utcfromtimestamp(open_time / 1000)
                candle = BinanceCandle(
                    timestamp=timestamp,
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                    quote_volume=float(row[7]),
                    trades=int(row[8])
                )
                candles.append(candle)
            except (ValueError, IndexError, OSError) as e:
                logger.warning(f"Failed to parse row: {row[:3]}..., error: {e}")
                continue

        return candles

    def check_pair_available(self, symbol: str, quote: str = "USDT") -> bool:
        """Check if a trading pair has historical data available."""
        pair = f"{symbol.upper()}{quote}"
        # Try to fetch the index page
        url = f"{self.BASE_URL}/monthly/klines/{pair}/1m/"

        try:
            response = self.session.head(url, timeout=10)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def get_listing_info(
        self,
        symbol: str,
        approximate_date: datetime,
        quote: str = "USDT"
    ) -> Dict:
        """
        Get comprehensive listing information for a token.

        Returns:
            Dict with first_candle, first_10_candles, first_hour_stats, etc.
        """
        pair = f"{symbol.upper()}{quote}"

        # Fetch the day's data
        candles = self._fetch_daily_klines(pair, approximate_date)

        if not candles:
            # Try monthly if daily not available
            candles = self._fetch_monthly_klines(pair, approximate_date)

        if not candles:
            return {"error": f"No data found for {pair}"}

        # Find the first candle of the day (likely listing time)
        candles.sort(key=lambda x: x.timestamp)
        first_candle = candles[0]

        # Get first 10 candles
        first_10 = candles[:10]

        # Get first hour (60 candles)
        first_hour = candles[:60]

        # Calculate stats
        first_hour_volume = sum(c.quote_volume for c in first_hour)
        first_hour_trades = sum(c.trades for c in first_hour)
        high_price = max(c.high for c in first_hour) if first_hour else 0
        low_price = min(c.low for c in first_hour) if first_hour else 0

        return {
            "pair": pair,
            "first_trade_time": first_candle.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "first_price": first_candle.open,
            "first_candle": {
                "time": first_candle.timestamp.strftime("%H:%M:%S"),
                "open": first_candle.open,
                "high": first_candle.high,
                "low": first_candle.low,
                "close": first_candle.close,
                "volume_usd": first_candle.quote_volume,
                "trades": first_candle.trades
            },
            "first_10_candles": [
                {
                    "minute": i + 1,
                    "time": c.timestamp.strftime("%H:%M:%S"),
                    "open": round(c.open, 6),
                    "high": round(c.high, 6),
                    "low": round(c.low, 6),
                    "close": round(c.close, 6)
                }
                for i, c in enumerate(first_10)
            ],
            "first_hour_stats": {
                "volume_usd": round(first_hour_volume, 2),
                "total_trades": first_hour_trades,
                "high": high_price,
                "low": low_price,
                "high_low_ratio": round(high_price / low_price, 2) if low_price > 0 else None
            }
        }


# Convenience function for quick lookups
def fetch_binance_tge_candles(
    symbol: str,
    tge_date: str,  # Format: "YYYY-MM-DD HH:MM:SS"
    num_candles: int = 10
) -> Tuple[List[Dict], Optional[str]]:
    """
    Quick function to fetch TGE candles from Binance.

    Example:
        candles, error = fetch_binance_tge_candles("JTO", "2023-12-07 16:00:00")
        if error:
            print(f"Error: {error}")
        else:
            for c in candles:
                print(f"Minute {c['minute']}: {c['open']} -> {c['close']}")
    """
    provider = BinanceHistoricalProvider()
    tge_dt = datetime.strptime(tge_date, "%Y-%m-%d %H:%M:%S")
    return provider.get_tge_candles(symbol, tge_dt, num_candles)


if __name__ == "__main__":
    # Test with JTO (launched Dec 7, 2023)
    import json

    logging.basicConfig(level=logging.INFO)

    provider = BinanceHistoricalProvider()

    # Test JTO
    print("=" * 60)
    print("Testing JTO (Dec 7, 2023)")
    print("=" * 60)

    jto_date = datetime(2023, 12, 7, 16, 0, 0)  # Approximate TGE time
    info = provider.get_listing_info("JTO", jto_date)
    print(json.dumps(info, indent=2, default=str))

    # Test EIGEN
    print("\n" + "=" * 60)
    print("Testing EIGEN (Oct 1, 2024)")
    print("=" * 60)

    eigen_date = datetime(2024, 10, 1, 4, 0, 0)
    info = provider.get_listing_info("EIGEN", eigen_date)
    print(json.dumps(info, indent=2, default=str))
