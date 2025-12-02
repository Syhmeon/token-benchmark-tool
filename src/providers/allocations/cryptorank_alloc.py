"""CryptoRank allocation data provider.

Fetches token allocation breakdowns from CryptoRank API.
Returns raw allocation data without mapping to canonical buckets.
"""

import logging
import time
from typing import Any

import httpx

from ...core.exceptions import DataSourceError, RateLimitError
from ...core.models import (
    RawAllocation,
    SourceReference,
    VestingTerms,
)
from ...core.types import DataSource, VestingScheduleType
from ..base import CachedProvider

logger = logging.getLogger(__name__)


class CryptoRankAllocationProvider(CachedProvider):
    """Fetches allocation data from CryptoRank API."""

    SOURCE = DataSource.CRYPTORANK
    BASE_URL = "https://api.cryptorank.io/v1"

    def __init__(
        self,
        api_key: str | None = None,
        rate_limit_calls: int = 30,
        rate_limit_period: int = 60,
        cache_ttl_seconds: int = 3600,
    ):
        """
        Initialize CryptoRank allocation provider.

        Args:
            api_key: CryptoRank API key
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

    def is_available(self) -> bool:
        """Check if CryptoRank API is available."""
        try:
            self._wait_for_rate_limit()
            with httpx.Client(timeout=10.0) as client:
                response = client.get(f"{self.BASE_URL}/global")
                return response.status_code == 200
        except Exception:
            return False

    def _make_request(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a rate-limited request to CryptoRank API."""
        self._wait_for_rate_limit()
        start_time = time.time()

        params = params or {}
        if self.api_key:
            params["api_key"] = self.api_key

        url = f"{self.BASE_URL}{endpoint}"

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(url, params=params)

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
                    source="cryptorank",
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
                source="cryptorank",
                message=f"HTTP {e.response.status_code}",
                endpoint=endpoint,
                status_code=e.response.status_code,
            )
        except httpx.RequestError as e:
            raise DataSourceError(
                source="cryptorank",
                message=str(e),
                endpoint=endpoint,
            )

    def search_project(self, query: str) -> list[dict[str, Any]]:
        """Search for projects matching a query."""
        data = self._make_request("/currencies", params={"search": query, "limit": 10})
        return data.get("data", [])

    def resolve_project_key(self, symbol_or_name: str) -> str | None:
        """Resolve a symbol/name to CryptoRank project key."""
        results = self.search_project(symbol_or_name)
        if not results:
            return None

        symbol_upper = symbol_or_name.upper()
        for project in results:
            if project.get("symbol", "").upper() == symbol_upper:
                return project.get("key")

        return results[0].get("key") if results else None

    def _parse_vesting(self, vesting_data: dict[str, Any] | None) -> VestingTerms | None:
        """
        Parse vesting information from CryptoRank data.

        Args:
            vesting_data: Raw vesting data from API

        Returns:
            VestingTerms or None
        """
        if not vesting_data:
            return None

        # Extract fields from various possible formats
        tge_unlock = vesting_data.get("tgeUnlock") or vesting_data.get("initialUnlock")
        cliff = vesting_data.get("cliff") or vesting_data.get("cliffMonths")
        vesting_duration = vesting_data.get("vestingMonths") or vesting_data.get("duration")
        schedule_raw = vesting_data.get("schedule") or vesting_data.get("type")
        description = vesting_data.get("description") or vesting_data.get("raw")

        # Parse schedule type
        schedule_type = VestingScheduleType.UNKNOWN
        if schedule_raw:
            schedule_lower = str(schedule_raw).lower()
            if "linear" in schedule_lower:
                schedule_type = VestingScheduleType.LINEAR
            elif "cliff" in schedule_lower and "linear" not in schedule_lower:
                schedule_type = VestingScheduleType.CLIFF
            elif "monthly" in schedule_lower or "quarterly" in schedule_lower:
                schedule_type = VestingScheduleType.STEP

        # Only create VestingTerms if we have some data
        if any([tge_unlock, cliff, vesting_duration, description]):
            return VestingTerms(
                tge_unlock_pct=float(tge_unlock) if tge_unlock else None,
                cliff_months=int(cliff) if cliff else None,
                vesting_months=int(vesting_duration) if vesting_duration else None,
                schedule_type=schedule_type,
                raw_description=description,
            )

        return None

    def get_allocations(
        self,
        project_key: str | None = None,
        symbol: str | None = None,
    ) -> list[RawAllocation]:
        """
        Get raw allocation data for a project.

        Args:
            project_key: CryptoRank project key (slug)
            symbol: Token symbol (will be resolved to key)

        Returns:
            List of RawAllocation objects
        """
        # Resolve key if symbol provided
        if project_key is None and symbol:
            project_key = self.resolve_project_key(symbol)

        if not project_key:
            logger.warning(f"Could not resolve project key for {symbol}")
            return []

        # Check cache
        cache_key = f"allocations:{project_key}"
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached

        # Fetch project data
        data = self._make_request(f"/currencies/{project_key}")

        if not data or "data" not in data:
            return []

        project_data = data["data"]

        # Extract token allocation data
        # CryptoRank may store this in different fields
        allocation_data = (
            project_data.get("tokenDistribution")
            or project_data.get("tokenomics", {}).get("distribution")
            or project_data.get("allocation")
            or []
        )

        if not allocation_data:
            logger.info(f"No allocation data found for {project_key}")
            return []

        source_ref = SourceReference(
            source=DataSource.CRYPTORANK,
            url=f"https://cryptorank.io/ico/{project_key}",
            endpoint=f"/currencies/{project_key}",
        )

        allocations = []
        for item in allocation_data:
            # Handle different data formats
            if isinstance(item, dict):
                label = item.get("name") or item.get("category") or item.get("label", "Unknown")
                percentage = item.get("percentage") or item.get("percent") or item.get("share")
                amount = item.get("amount") or item.get("tokens")
                vesting_raw = item.get("vesting") or item.get("vestingSchedule")
            else:
                continue

            # Parse vesting
            vesting = self._parse_vesting(vesting_raw) if vesting_raw else None

            allocation = RawAllocation(
                source=DataSource.CRYPTORANK,
                label=str(label),
                percentage=float(percentage) if percentage else None,
                amount=float(amount) if amount else None,
                vesting=vesting,
                source_reference=source_ref,
            )
            allocations.append(allocation)

        self._set_cache(cache_key, allocations)
        return allocations

    def get_allocations_by_coingecko_id(
        self,
        coingecko_id: str,
    ) -> list[RawAllocation]:
        """
        Get allocations using CoinGecko ID.

        Args:
            coingecko_id: CoinGecko token ID

        Returns:
            List of RawAllocation objects
        """
        return self.get_allocations(symbol=coingecko_id)
