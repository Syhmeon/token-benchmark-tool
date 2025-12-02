"""CryptoRank fundraising data provider.

CryptoRank provides comprehensive fundraising data including:
- Total raised amounts
- Individual funding rounds
- Investor lists
- Token allocations (handled separately)

API documentation: https://api.cryptorank.io/v1/
"""

import logging
import time
from datetime import datetime
from typing import Any

import httpx

from ...core.exceptions import DataSourceError, RateLimitError, TokenNotFoundError
from ...core.models import (
    FundraisingData,
    FundraisingRound,
    SourceReference,
)
from ...core.types import DataSource
from ..base import CachedProvider

logger = logging.getLogger(__name__)


class CryptoRankFundraisingProvider(CachedProvider):
    """Fetches fundraising data from CryptoRank API."""

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
        Initialize CryptoRank provider.

        Args:
            api_key: CryptoRank API key (optional for basic endpoints)
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
        """
        Search for projects matching a query.

        Args:
            query: Search string (symbol or name)

        Returns:
            List of matching projects
        """
        data = self._make_request("/currencies", params={"search": query, "limit": 10})
        return data.get("data", [])

    def resolve_project_key(self, symbol_or_name: str) -> str | None:
        """
        Resolve a symbol/name to CryptoRank project key.

        Args:
            symbol_or_name: Token symbol or name

        Returns:
            CryptoRank project key (slug) or None
        """
        results = self.search_project(symbol_or_name)

        if not results:
            return None

        # Try exact symbol match first
        symbol_upper = symbol_or_name.upper()
        for project in results:
            if project.get("symbol", "").upper() == symbol_upper:
                return project.get("key")

        # Fall back to first result
        return results[0].get("key") if results else None

    def get_fundraising(
        self,
        project_key: str | None = None,
        symbol: str | None = None,
    ) -> FundraisingData | None:
        """
        Get fundraising data for a project.

        Args:
            project_key: CryptoRank project key (slug)
            symbol: Token symbol (will be resolved to key)

        Returns:
            FundraisingData or None if not found
        """
        # Resolve key if symbol provided
        if project_key is None and symbol:
            project_key = self.resolve_project_key(symbol)

        if not project_key:
            logger.warning(f"Could not resolve project key for {symbol}")
            return None

        # Check cache
        cache_key = f"fundraising:{project_key}"
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached

        # Fetch project data
        data = self._make_request(f"/currencies/{project_key}")

        if not data or "data" not in data:
            return None

        project_data = data["data"]

        # Extract fundraising information
        fundraising_info = project_data.get("fundingRounds", [])
        total_raised = None

        # Calculate total raised from rounds
        rounds = []
        calculated_total = 0.0

        for round_data in fundraising_info:
            round_amount = round_data.get("raise")
            if round_amount:
                calculated_total += float(round_amount)

            # Parse date
            round_date = None
            date_str = round_data.get("date")
            if date_str:
                try:
                    round_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                except ValueError:
                    pass

            # Parse investors
            investors = []
            lead_investors = []
            for investor in round_data.get("investors", []):
                investor_name = investor.get("name", "")
                if investor_name:
                    investors.append(investor_name)
                    if investor.get("isLead"):
                        lead_investors.append(investor_name)

            round_obj = FundraisingRound(
                round_name=round_data.get("roundType", "Unknown"),
                amount_usd=round_amount,
                date=round_date,
                valuation_usd=round_data.get("valuation"),
                token_price=round_data.get("tokenPrice"),
                investors=investors,
                lead_investors=lead_investors,
            )
            rounds.append(round_obj)

        # Use calculated total if not provided directly
        if calculated_total > 0:
            total_raised = calculated_total

        source_ref = SourceReference(
            source=DataSource.CRYPTORANK,
            url=f"https://cryptorank.io/ico/{project_key}",
            endpoint=f"/currencies/{project_key}",
        )

        result = FundraisingData(
            total_raised_usd=total_raised,
            rounds=rounds,
            source=source_ref,
        )

        self._set_cache(cache_key, result)
        return result

    def get_fundraising_by_coingecko_id(
        self,
        coingecko_id: str,
    ) -> FundraisingData | None:
        """
        Get fundraising data using CoinGecko ID.

        CryptoRank uses its own project keys, so we attempt to
        match via symbol search.

        Args:
            coingecko_id: CoinGecko token ID

        Returns:
            FundraisingData or None
        """
        # CoinGecko IDs are often similar to project names
        # Try the ID as search term
        return self.get_fundraising(symbol=coingecko_id)
