"""CoinMarketCap API Provider.

Provides:
- Current price data (backup for CoinGecko)
- Token metadata (tags, description, links)
- Market data (market cap, volume, supply)

API documentation: https://coinmarketcap.com/api/documentation/v1/
Basic plan: 10,000 credits/month, 30 req/min, 14 endpoints
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

import httpx

from ...core.config import get_config
from ...core.exceptions import DataSourceError, RateLimitError, TokenNotFoundError
from ...core.models import SourceReference
from ...core.types import DataSource
from ..base import CachedProvider

logger = logging.getLogger(__name__)


@dataclass
class CMCQuoteData:
    """CoinMarketCap quote data."""

    cmc_id: int
    symbol: str
    name: str
    slug: str

    # Supply
    circulating_supply: Optional[float]
    total_supply: Optional[float]
    max_supply: Optional[float]

    # Price data
    price_usd: float
    volume_24h: float
    market_cap: float
    fully_diluted_market_cap: Optional[float]

    # Changes
    percent_change_1h: Optional[float]
    percent_change_24h: Optional[float]
    percent_change_7d: Optional[float]
    percent_change_30d: Optional[float]

    # Metadata
    cmc_rank: Optional[int]
    num_market_pairs: int
    date_added: Optional[datetime]
    platform: Optional[str]
    token_address: Optional[str]
    tags: list[str]

    last_updated: datetime
    source: Optional[SourceReference] = None


@dataclass
class CMCTokenInfo:
    """CoinMarketCap token info/metadata."""

    cmc_id: int
    symbol: str
    name: str
    slug: str
    category: str
    description: str
    logo: str

    # Links
    website: list[str]
    twitter: list[str]
    discord: list[str]
    telegram: list[str]
    explorer: list[str]

    # Platform
    platform: Optional[str]
    token_address: Optional[str]

    tags: list[str]
    source: Optional[SourceReference] = None


class CoinMarketCapProvider(CachedProvider):
    """CoinMarketCap API provider for price and metadata."""

    SOURCE = DataSource.COINMARKETCAP
    BASE_URL = "https://pro-api.coinmarketcap.com"

    def __init__(
        self,
        api_key: Optional[str] = None,
        rate_limit_calls: int = 25,  # Stay under 30/min limit
        rate_limit_period: int = 60,
        cache_ttl_seconds: int = 300,  # 5 min cache for price data
    ):
        """
        Initialize CoinMarketCap provider.

        Args:
            api_key: CMC API key (loaded from config if not provided)
            rate_limit_calls: Rate limit per period
            rate_limit_period: Period in seconds
            cache_ttl_seconds: Cache TTL
        """
        super().__init__(
            rate_limit_calls=rate_limit_calls,
            rate_limit_period=rate_limit_period,
            cache_ttl_seconds=cache_ttl_seconds,
        )
        self.api_key = api_key or get_config().coinmarketcap_api_key

    def is_available(self) -> bool:
        """Check if CMC API is available."""
        if not self.api_key:
            return False
        try:
            self._wait_for_rate_limit()
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    f"{self.BASE_URL}/v1/key/info",
                    headers={"X-CMC_PRO_API_KEY": self.api_key}
                )
                return response.status_code == 200
        except Exception:
            return False

    def _make_request(
        self,
        endpoint: str,
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Make a rate-limited request to CMC API."""
        if not self.api_key:
            raise DataSourceError(
                source="coinmarketcap",
                message="API key not configured",
            )

        self._wait_for_rate_limit()

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(
                    f"{self.BASE_URL}{endpoint}",
                    params=params,
                    headers={"X-CMC_PRO_API_KEY": self.api_key}
                )

                if response.status_code == 429:
                    raise RateLimitError(
                        source="coinmarketcap",
                        retry_after=60,
                    )

                if response.status_code == 401:
                    raise DataSourceError(
                        source="coinmarketcap",
                        message="Invalid API key",
                    )

                if response.status_code != 200:
                    raise DataSourceError(
                        source="coinmarketcap",
                        message=f"HTTP {response.status_code}",
                        endpoint=endpoint,
                    )

                return response.json()

        except httpx.RequestError as e:
            raise DataSourceError(
                source="coinmarketcap",
                message=str(e),
                endpoint=endpoint,
            )

    def get_quote(self, symbol: str) -> Optional[CMCQuoteData]:
        """
        Get current quote data for a token.

        Args:
            symbol: Token symbol (e.g., "JTO", "BTC")

        Returns:
            CMCQuoteData or None if not found
        """
        cache_key = f"quote:{symbol.upper()}"
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached

        try:
            data = self._make_request(
                "/v1/cryptocurrency/quotes/latest",
                params={"symbol": symbol.upper()}
            )
        except DataSourceError:
            return None

        if "data" not in data or symbol.upper() not in data["data"]:
            return None

        token_data = data["data"][symbol.upper()]
        quote = token_data.get("quote", {}).get("USD", {})

        # Parse date_added
        date_added = None
        if token_data.get("date_added"):
            try:
                date_added = datetime.fromisoformat(
                    token_data["date_added"].replace("Z", "+00:00")
                )
            except ValueError:
                pass

        # Parse last_updated
        last_updated = datetime.now()
        if quote.get("last_updated"):
            try:
                last_updated = datetime.fromisoformat(
                    quote["last_updated"].replace("Z", "+00:00")
                )
            except ValueError:
                pass

        # Platform info
        platform = token_data.get("platform")
        platform_name = platform.get("name") if platform else None
        token_address = platform.get("token_address") if platform else None

        result = CMCQuoteData(
            cmc_id=token_data.get("id"),
            symbol=token_data.get("symbol"),
            name=token_data.get("name"),
            slug=token_data.get("slug"),
            circulating_supply=token_data.get("circulating_supply"),
            total_supply=token_data.get("total_supply"),
            max_supply=token_data.get("max_supply"),
            price_usd=quote.get("price", 0),
            volume_24h=quote.get("volume_24h", 0),
            market_cap=quote.get("market_cap", 0),
            fully_diluted_market_cap=quote.get("fully_diluted_market_cap"),
            percent_change_1h=quote.get("percent_change_1h"),
            percent_change_24h=quote.get("percent_change_24h"),
            percent_change_7d=quote.get("percent_change_7d"),
            percent_change_30d=quote.get("percent_change_30d"),
            cmc_rank=token_data.get("cmc_rank"),
            num_market_pairs=token_data.get("num_market_pairs", 0),
            date_added=date_added,
            platform=platform_name,
            token_address=token_address,
            tags=token_data.get("tags", []),
            last_updated=last_updated,
            source=SourceReference(
                source=DataSource.COINMARKETCAP,
                url=f"https://coinmarketcap.com/currencies/{token_data.get('slug')}/",
                endpoint="/v1/cryptocurrency/quotes/latest",
            ),
        )

        self._set_cache(cache_key, result)
        return result

    def get_info(self, symbol: str) -> Optional[CMCTokenInfo]:
        """
        Get token metadata/info.

        Args:
            symbol: Token symbol (e.g., "JTO", "BTC")

        Returns:
            CMCTokenInfo or None if not found
        """
        cache_key = f"info:{symbol.upper()}"
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached

        try:
            data = self._make_request(
                "/v1/cryptocurrency/info",
                params={"symbol": symbol.upper()}
            )
        except DataSourceError:
            return None

        if "data" not in data or symbol.upper() not in data["data"]:
            return None

        token_data = data["data"][symbol.upper()]
        urls = token_data.get("urls", {})

        # Platform info
        platform = token_data.get("platform")
        platform_name = platform.get("name") if platform else None
        token_address = platform.get("token_address") if platform else None

        result = CMCTokenInfo(
            cmc_id=token_data.get("id"),
            symbol=token_data.get("symbol"),
            name=token_data.get("name"),
            slug=token_data.get("slug"),
            category=token_data.get("category", ""),
            description=token_data.get("description", ""),
            logo=token_data.get("logo", ""),
            website=urls.get("website", []),
            twitter=urls.get("twitter", []),
            discord=[u for u in urls.get("chat", []) if "discord" in u.lower()],
            telegram=[u for u in urls.get("chat", []) if "t.me" in u.lower() or "telegram" in u.lower()],
            explorer=urls.get("explorer", []),
            platform=platform_name,
            token_address=token_address,
            tags=token_data.get("tags", []),
            source=SourceReference(
                source=DataSource.COINMARKETCAP,
                url=f"https://coinmarketcap.com/currencies/{token_data.get('slug')}/",
                endpoint="/v1/cryptocurrency/info",
            ),
        )

        self._set_cache(cache_key, result)
        return result

    def get_price(self, symbol: str) -> Optional[float]:
        """
        Get current price for a token.

        Args:
            symbol: Token symbol

        Returns:
            Current price in USD or None
        """
        quote = self.get_quote(symbol)
        return quote.price_usd if quote else None

    def get_market_cap(self, symbol: str) -> Optional[float]:
        """
        Get current market cap for a token.

        Args:
            symbol: Token symbol

        Returns:
            Market cap in USD or None
        """
        quote = self.get_quote(symbol)
        return quote.market_cap if quote else None

    def get_fdv(self, symbol: str) -> Optional[float]:
        """
        Get fully diluted valuation for a token.

        Args:
            symbol: Token symbol

        Returns:
            FDV in USD or None
        """
        quote = self.get_quote(symbol)
        return quote.fully_diluted_market_cap if quote else None
