"""Token resolution - resolves user input to CoinGecko IDs and metadata.

This module handles the ambiguity of token identification:
- User might provide a symbol (ARB), CoinGecko ID (arbitrum), or address
- Symbols can be ambiguous (multiple tokens with same symbol)
- Need to fetch metadata for further processing
"""

import logging
import time
from datetime import datetime
from typing import Any

import httpx

from ..core.exceptions import DataSourceError, RateLimitError, TokenNotFoundError
from ..core.models import SourceReference, TokenInfo
from ..core.types import DataSource

logger = logging.getLogger(__name__)


class TokenResolver:
    """Resolves token identifiers to CoinGecko IDs with metadata."""

    COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"

    def __init__(
        self,
        api_key: str | None = None,
        rate_limit_calls: int = 30,
        rate_limit_period: int = 60,
    ):
        """
        Initialize the token resolver.

        Args:
            api_key: CoinGecko API key (optional, for pro tier)
            rate_limit_calls: Max calls per rate limit period
            rate_limit_period: Rate limit period in seconds
        """
        self.api_key = api_key
        self.rate_limit_calls = rate_limit_calls
        self.rate_limit_period = rate_limit_period
        self._call_timestamps: list[float] = []

        # Use pro API URL if key is provided
        if api_key:
            self.base_url = "https://pro-api.coingecko.com/api/v3"
        else:
            self.base_url = self.COINGECKO_BASE_URL

    def _wait_for_rate_limit(self) -> None:
        """Wait if rate limit would be exceeded."""
        now = time.time()
        # Remove old timestamps
        self._call_timestamps = [
            ts for ts in self._call_timestamps if now - ts < self.rate_limit_period
        ]
        if len(self._call_timestamps) >= self.rate_limit_calls:
            sleep_time = self._call_timestamps[0] + self.rate_limit_period - now
            if sleep_time > 0:
                logger.debug(f"Rate limit: sleeping {sleep_time:.1f}s")
                time.sleep(sleep_time)
        self._call_timestamps.append(time.time())

    def _make_request(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a rate-limited request to CoinGecko API."""
        self._wait_for_rate_limit()

        headers = {}
        if self.api_key:
            headers["x-cg-pro-api-key"] = self.api_key

        url = f"{self.base_url}{endpoint}"
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(url, params=params, headers=headers)

            if response.status_code == 429:
                raise RateLimitError(
                    source="coingecko",
                    retry_after_seconds=60,
                    endpoint=endpoint,
                )

            if response.status_code == 404:
                return {}  # Not found, return empty

            response.raise_for_status()
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

    def search(self, query: str) -> list[dict[str, Any]]:
        """
        Search for tokens matching a query.

        Args:
            query: Search string (symbol, name, or partial match)

        Returns:
            List of matching tokens with basic info
        """
        data = self._make_request("/search", params={"query": query})
        return data.get("coins", [])

    def get_coin_by_id(self, coingecko_id: str) -> dict[str, Any]:
        """
        Get detailed coin information by CoinGecko ID.

        Args:
            coingecko_id: CoinGecko identifier (e.g., "arbitrum")

        Returns:
            Detailed coin data including supply, categories, genesis date
        """
        return self._make_request(
            f"/coins/{coingecko_id}",
            params={
                "localization": "false",
                "tickers": "false",
                "market_data": "true",
                "community_data": "false",
                "developer_data": "false",
            },
        )

    def resolve(self, identifier: str) -> TokenInfo:
        """
        Resolve a token identifier to full TokenInfo.

        The identifier can be:
        - CoinGecko ID (e.g., "arbitrum")
        - Symbol (e.g., "ARB")
        - Contract address (future support)

        Args:
            identifier: Token identifier string

        Returns:
            TokenInfo with resolved metadata

        Raises:
            TokenNotFoundError: If token cannot be found
        """
        identifier = identifier.strip().lower()
        logger.info(f"Resolving token: {identifier}")

        # First, try as CoinGecko ID directly
        coin_data = self.get_coin_by_id(identifier)
        if coin_data:
            return self._parse_coin_data(coin_data)

        # If not found, search for it
        search_results = self.search(identifier)
        if not search_results:
            raise TokenNotFoundError(identifier, sources_checked=["coingecko"])

        # Try to find exact symbol match
        exact_matches = [
            r for r in search_results if r.get("symbol", "").lower() == identifier
        ]

        if len(exact_matches) == 1:
            # Single exact match - use it
            coin_id = exact_matches[0]["id"]
        elif len(exact_matches) > 1:
            # Multiple matches - prefer by market cap rank
            exact_matches.sort(key=lambda x: x.get("market_cap_rank") or 9999)
            coin_id = exact_matches[0]["id"]
            logger.warning(
                f"Multiple tokens with symbol '{identifier}', "
                f"using highest ranked: {coin_id}"
            )
        else:
            # No exact match - use first search result
            coin_id = search_results[0]["id"]
            logger.warning(
                f"No exact symbol match for '{identifier}', "
                f"using best search result: {coin_id}"
            )

        # Fetch full coin data
        coin_data = self.get_coin_by_id(coin_id)
        if not coin_data:
            raise TokenNotFoundError(identifier, sources_checked=["coingecko"])

        return self._parse_coin_data(coin_data)

    def _parse_coin_data(self, data: dict[str, Any]) -> TokenInfo:
        """Parse CoinGecko coin data into TokenInfo model."""
        # Extract contract addresses (platforms)
        contract_addresses = {}
        platforms = data.get("platforms", {})
        for chain, address in platforms.items():
            if address:  # Skip empty addresses
                contract_addresses[chain] = address

        # Parse genesis date if available
        genesis_date = None
        if data.get("genesis_date"):
            try:
                genesis_date = datetime.strptime(data["genesis_date"], "%Y-%m-%d")
            except ValueError:
                logger.warning(f"Could not parse genesis date: {data['genesis_date']}")

        # Create source reference
        source_ref = SourceReference(
            source=DataSource.COINGECKO,
            url=f"https://www.coingecko.com/en/coins/{data['id']}",
            endpoint=f"/coins/{data['id']}",
            raw_response=data,
        )

        return TokenInfo(
            coingecko_id=data["id"],
            symbol=data.get("symbol", "").upper(),
            name=data.get("name", ""),
            contract_addresses=contract_addresses,
            categories=data.get("categories", []) or [],
            genesis_date=genesis_date,
            source=source_ref,
        )

    def get_coin_list(self, include_platform: bool = True) -> list[dict[str, Any]]:
        """
        Get full list of coins (for building local cache).

        Args:
            include_platform: Include contract addresses in response

        Returns:
            List of all coins with basic info
        """
        return self._make_request(
            "/coins/list",
            params={"include_platform": str(include_platform).lower()},
        )
