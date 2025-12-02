"""CoinGecko price provider for historical daily OHLC data.

This provider fetches historical price data from CoinGecko API.
It serves as a fallback when exchange data is unavailable or
for cross-validation of prices.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from ...core.exceptions import DataSourceError, RateLimitError
from ...core.models import ExchangeCandle, ExchangeListing, SourceReference
from ...core.types import DataSource
from ..base import CachedProvider

logger = logging.getLogger(__name__)


class CoinGeckoPriceProvider(CachedProvider):
    """Fetches historical price data from CoinGecko."""

    SOURCE = DataSource.COINGECKO
    BASE_URL = "https://api.coingecko.com/api/v3"

    def __init__(
        self,
        api_key: str | None = None,
        rate_limit_calls: int = 30,
        rate_limit_period: int = 60,
        cache_ttl_seconds: int = 3600,
    ):
        """
        Initialize CoinGecko price provider.

        Args:
            api_key: Optional CoinGecko Pro API key
            rate_limit_calls: Rate limit per period
            rate_limit_period: Period in seconds
            cache_ttl_seconds: Cache TTL
        """
        super().__init__(
            rate_limit_calls=rate_limit_calls,
            rate_limit_period=rate_limit_period,
            cache_ttl_seconds=cache_ttl_seconds,
        )
        self.api_key = api_key
        if api_key:
            self.base_url = "https://pro-api.coingecko.com/api/v3"
        else:
            self.base_url = self.BASE_URL

    def is_available(self) -> bool:
        """Check if CoinGecko API is available."""
        try:
            self._wait_for_rate_limit()
            with httpx.Client(timeout=10.0) as client:
                response = client.get(f"{self.base_url}/ping")
                return response.status_code == 200
        except Exception:
            return False

    def _make_request(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Make a rate-limited request to CoinGecko."""
        self._wait_for_rate_limit()
        start_time = time.time()

        headers = {}
        if self.api_key:
            headers["x-cg-pro-api-key"] = self.api_key

        url = f"{self.base_url}{endpoint}"

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(url, params=params, headers=headers)

            duration_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 429:
                self._record_audit(
                    action="fetch",
                    endpoint=endpoint,
                    success=False,
                    error_message="Rate limit exceeded",
                    duration_ms=duration_ms,
                )
                raise RateLimitError(
                    source="coingecko",
                    retry_after_seconds=60,
                    endpoint=endpoint,
                )

            if response.status_code == 404:
                return {}

            response.raise_for_status()

            self._record_audit(
                action="fetch",
                endpoint=endpoint,
                success=True,
                duration_ms=duration_ms,
            )

            return response.json()

        except httpx.HTTPStatusError as e:
            raise DataSourceError(
                source="coingecko",
                message=f"HTTP {e.response.status_code}",
                endpoint=endpoint,
                status_code=e.response.status_code,
            )
        except httpx.RequestError as e:
            raise DataSourceError(
                source="coingecko",
                message=str(e),
                endpoint=endpoint,
            )

    def get_historical_ohlc(
        self,
        coingecko_id: str,
        days: int = 365,
        vs_currency: str = "usd",
    ) -> list[ExchangeCandle]:
        """
        Get historical OHLC data for a token.

        Note: CoinGecko OHLC endpoint returns candles at different
        granularities depending on the 'days' parameter:
        - 1-2 days: 30m candles
        - 3-30 days: 4h candles
        - 31+ days: 4d candles

        Args:
            coingecko_id: CoinGecko token ID
            days: Number of days of history (1-365 for free tier)
            vs_currency: Quote currency

        Returns:
            List of ExchangeCandle objects
        """
        cache_key = f"ohlc:{coingecko_id}:{days}:{vs_currency}"
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached

        data = self._make_request(
            f"/coins/{coingecko_id}/ohlc",
            params={"vs_currency": vs_currency, "days": str(days)},
        )

        if not data or not isinstance(data, list):
            return []

        candles = []
        for ohlc in data:
            if len(ohlc) >= 5:
                candle = ExchangeCandle(
                    timestamp=datetime.fromtimestamp(ohlc[0] / 1000, tz=timezone.utc),
                    open=float(ohlc[1]),
                    high=float(ohlc[2]),
                    low=float(ohlc[3]),
                    close=float(ohlc[4]),
                    volume=0.0,  # OHLC endpoint doesn't include volume
                )
                candles.append(candle)

        self._set_cache(cache_key, candles)
        return candles

    def get_market_chart(
        self,
        coingecko_id: str,
        days: int = 365,
        vs_currency: str = "usd",
    ) -> dict[str, list[tuple[int, float]]]:
        """
        Get market chart data (prices, market caps, volumes).

        This endpoint provides daily data and includes volume,
        unlike the OHLC endpoint.

        Args:
            coingecko_id: CoinGecko token ID
            days: Number of days
            vs_currency: Quote currency

        Returns:
            Dict with 'prices', 'market_caps', 'total_volumes' keys
        """
        cache_key = f"market_chart:{coingecko_id}:{days}:{vs_currency}"
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached

        data = self._make_request(
            f"/coins/{coingecko_id}/market_chart",
            params={"vs_currency": vs_currency, "days": str(days)},
        )

        if not data or not isinstance(data, dict):
            return {}

        self._set_cache(cache_key, data)
        return data

    def get_listing_data(
        self,
        coingecko_id: str,
        listing_date_hint: datetime | None = None,
    ) -> ExchangeListing | None:
        """
        Get listing data from CoinGecko historical prices.

        This creates an ExchangeListing-compatible structure from
        CoinGecko's historical data, useful as fallback when
        exchange data is unavailable.

        Args:
            coingecko_id: CoinGecko token ID
            listing_date_hint: Optional date to search near

        Returns:
            ExchangeListing or None if no data
        """
        # Fetch max history to find earliest data point
        chart_data = self.get_market_chart(coingecko_id, days=365)

        if not chart_data or "prices" not in chart_data:
            return None

        prices = chart_data["prices"]
        volumes = chart_data.get("total_volumes", [])

        if not prices:
            return None

        # Find earliest price point
        earliest = prices[0]
        earliest_timestamp = datetime.fromtimestamp(earliest[0] / 1000, tz=timezone.utc)
        earliest_price = earliest[1]

        # Get corresponding volume if available
        earliest_volume = 0.0
        if volumes:
            earliest_volume = volumes[0][1] if volumes[0] else 0.0

        first_candle = ExchangeCandle(
            timestamp=earliest_timestamp,
            open=earliest_price,
            high=earliest_price,  # Daily data, approximate
            low=earliest_price,
            close=earliest_price,
            volume=earliest_volume,
            volume_usd=earliest_volume,
        )

        source_ref = SourceReference(
            source=DataSource.COINGECKO,
            url=f"https://www.coingecko.com/en/coins/{coingecko_id}",
            endpoint=f"/coins/{coingecko_id}/market_chart",
        )

        return ExchangeListing(
            exchange="coingecko",
            trading_pair=f"{coingecko_id.upper()}/USD",
            base_currency=coingecko_id.upper(),
            quote_currency="USD",
            first_candle=first_candle,
            timeframe="1d",  # CoinGecko provides daily data
            source=source_ref,
        )

    def get_price_at_date(
        self,
        coingecko_id: str,
        date: datetime,
        vs_currency: str = "usd",
    ) -> float | None:
        """
        Get price at a specific date.

        Args:
            coingecko_id: CoinGecko token ID
            date: Target date
            vs_currency: Quote currency

        Returns:
            Price at date or None
        """
        date_str = date.strftime("%d-%m-%Y")

        data = self._make_request(
            f"/coins/{coingecko_id}/history",
            params={"date": date_str},
        )

        if not data or "market_data" not in data:
            return None

        market_data = data["market_data"]
        current_price = market_data.get("current_price", {})

        return current_price.get(vs_currency)
