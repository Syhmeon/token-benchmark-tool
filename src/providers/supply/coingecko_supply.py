"""CoinGecko supply data provider.

Fetches token supply information (total, max, circulating) from CoinGecko.
Note that CoinGecko provides CURRENT supply, not historical supply at listing.
Historical circulating supply at listing requires manual override or estimation.
"""

import logging
import time
from typing import Any

import httpx

from ...core.exceptions import DataSourceError, RateLimitError
from ...core.models import SourceReference, SupplyData
from ...core.types import DataSource
from ..base import CachedProvider

logger = logging.getLogger(__name__)


class CoinGeckoSupplyProvider(CachedProvider):
    """Fetches supply data from CoinGecko."""

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
        Initialize CoinGecko supply provider.

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
    ) -> dict[str, Any]:
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

    def get_supply(
        self,
        coingecko_id: str,
        manual_circulating_at_listing: float | None = None,
    ) -> SupplyData:
        """
        Get supply data for a token.

        Args:
            coingecko_id: CoinGecko token ID
            manual_circulating_at_listing: Optional manual override for
                circulating supply at listing time

        Returns:
            SupplyData with current supply information

        Note:
            CoinGecko only provides CURRENT supply. For accurate
            initial market cap, you should provide manual_circulating_at_listing
            or use estimation based on tokenomics data.
        """
        cache_key = f"supply:{coingecko_id}"
        cached = self._get_from_cache(cache_key)

        # Only use cache if no manual override provided
        if cached is not None and manual_circulating_at_listing is None:
            return cached

        # Fetch coin data
        data = self._make_request(
            f"/coins/{coingecko_id}",
            params={
                "localization": "false",
                "tickers": "false",
                "market_data": "true",
                "community_data": "false",
                "developer_data": "false",
            },
        )

        if not data or "market_data" not in data:
            logger.warning(f"No market data available for {coingecko_id}")
            return SupplyData(
                circulating_supply_source=DataSource.UNKNOWN,
                circulating_supply_is_estimate=True,
            )

        market_data = data["market_data"]

        # Extract supply values
        total_supply = market_data.get("total_supply")
        max_supply = market_data.get("max_supply")
        circulating_supply = market_data.get("circulating_supply")

        # Determine circulating supply at listing
        if manual_circulating_at_listing is not None:
            circ_at_listing = manual_circulating_at_listing
            circ_source = DataSource.MANUAL
            is_estimate = False
            estimation_method = "Manual override provided by analyst"
        else:
            # Current circulating is NOT the same as at-listing
            # Flag this clearly
            circ_at_listing = None  # Unknown
            circ_source = DataSource.UNKNOWN
            is_estimate = True
            estimation_method = (
                "Circulating supply at listing is unknown. "
                "Current circulating supply available but not used. "
                "Provide manual override for accurate initial market cap."
            )

        source_ref = SourceReference(
            source=DataSource.COINGECKO,
            url=f"https://www.coingecko.com/en/coins/{coingecko_id}",
            endpoint=f"/coins/{coingecko_id}",
        )

        supply_data = SupplyData(
            total_supply=total_supply,
            max_supply=max_supply,
            circulating_supply_current=circulating_supply,
            circulating_supply_at_listing=circ_at_listing,
            circulating_supply_source=circ_source,
            circulating_supply_is_estimate=is_estimate,
            estimation_method=estimation_method,
            source=source_ref,
        )

        # Cache the base data (without manual override)
        if manual_circulating_at_listing is None:
            self._set_cache(cache_key, supply_data)

        return supply_data

    def get_supply_with_estimate(
        self,
        coingecko_id: str,
        tge_unlock_percentage: float | None = None,
    ) -> SupplyData:
        """
        Get supply data with estimated circulating at listing.

        If tge_unlock_percentage is provided, estimates initial circulating
        supply as: total_supply * (tge_unlock_percentage / 100)

        Args:
            coingecko_id: CoinGecko token ID
            tge_unlock_percentage: Percentage unlocked at TGE (0-100)

        Returns:
            SupplyData with estimated circulating supply at listing

        Warning:
            This estimation is approximate. Real TGE circulating depends on
            multiple allocation categories with different unlock schedules.
        """
        base_supply = self.get_supply(coingecko_id)

        if tge_unlock_percentage is None or base_supply.total_supply is None:
            return base_supply

        # Estimate circulating at listing
        estimated_circulating = base_supply.total_supply * (tge_unlock_percentage / 100)

        return SupplyData(
            total_supply=base_supply.total_supply,
            max_supply=base_supply.max_supply,
            circulating_supply_current=base_supply.circulating_supply_current,
            circulating_supply_at_listing=estimated_circulating,
            circulating_supply_source=DataSource.ESTIMATED,
            circulating_supply_is_estimate=True,
            estimation_method=(
                f"Estimated from TGE unlock percentage ({tge_unlock_percentage}%) "
                f"applied to total supply. "
                f"Formula: {base_supply.total_supply:,.0f} × {tge_unlock_percentage}% = "
                f"{estimated_circulating:,.0f}"
            ),
            source=base_supply.source,
        )
