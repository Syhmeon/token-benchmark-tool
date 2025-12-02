"""DropsTab API Provider for token unlocks and fundraising data.

DropsTab provides comprehensive data on:
- Token unlock schedules
- Fundraising rounds
- VC/Investor information
- Market data

API Documentation: https://api-docs.dropstab.com/
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import httpx

from ...core.config import get_config
from ...core.exceptions import DataSourceError, RateLimitError
from ...core.models import FundraisingRound, SourceReference
from ...core.types import DataSource
from ..base import CachedProvider

logger = logging.getLogger(__name__)


@dataclass
class TokenUnlockEvent:
    """A token unlock event."""
    date: datetime
    amount: float
    percentage: float
    allocation: str
    is_cliff: bool = False


@dataclass
class TokenUnlockSchedule:
    """Complete token unlock schedule."""
    token_symbol: str
    token_name: str
    total_supply: float
    circulating_supply: float
    unlocked_percentage: float
    upcoming_unlocks: list[TokenUnlockEvent] = field(default_factory=list)
    allocations: dict[str, float] = field(default_factory=dict)
    source: Optional[SourceReference] = None


@dataclass
class FundraisingData:
    """Fundraising data from DropsTab."""
    total_raised_usd: Optional[float]
    rounds: list[FundraisingRound] = field(default_factory=list)
    investors: list[str] = field(default_factory=list)
    lead_investors: list[str] = field(default_factory=list)
    source: Optional[SourceReference] = None


class DropsTabProvider(CachedProvider):
    """Fetches token unlock and fundraising data from DropsTab API."""

    SOURCE = DataSource.DROPSTAB
    BASE_URL = "https://public-api.dropstab.com/api/v1"

    def __init__(
        self,
        api_key: Optional[str] = None,
        rate_limit_calls: int = 30,
        rate_limit_period: int = 60,
        cache_ttl_seconds: int = 3600,
    ):
        """
        Initialize DropsTab provider.

        Args:
            api_key: DropsTab API key (loaded from config if not provided)
            rate_limit_calls: Rate limit per period
            rate_limit_period: Period in seconds
            cache_ttl_seconds: Cache TTL
        """
        super().__init__(
            rate_limit_calls=rate_limit_calls,
            rate_limit_period=rate_limit_period,
            cache_ttl_seconds=cache_ttl_seconds,
        )
        self.api_key = api_key or get_config().dropstab_api_key

    def is_available(self) -> bool:
        """Check if DropsTab API is available and configured."""
        if not self.api_key:
            return False

        try:
            self._wait_for_rate_limit()
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    f"{self.BASE_URL}/coins/supported",
                    headers=self._get_headers(),
                )
                return response.status_code == 200
        except Exception:
            return False

    def _get_headers(self) -> dict[str, str]:
        """Get request headers with API key."""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _make_request(
        self,
        endpoint: str,
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Make a rate-limited request to DropsTab API."""
        self._wait_for_rate_limit()
        start_time = time.time()

        url = f"{self.BASE_URL}{endpoint}"

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(
                    url,
                    params=params,
                    headers=self._get_headers(),
                )

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
                    source="dropstab",
                    retry_after_seconds=60,
                    endpoint=endpoint,
                )

            if response.status_code == 404:
                return {}

            if response.status_code == 401:
                raise DataSourceError(
                    source="dropstab",
                    message="Invalid API key",
                    endpoint=endpoint,
                    status_code=401,
                )

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
                source="dropstab",
                message=f"HTTP {e.response.status_code}",
                endpoint=endpoint,
                status_code=e.response.status_code,
            )
        except httpx.RequestError as e:
            raise DataSourceError(
                source="dropstab",
                message=str(e),
                endpoint=endpoint,
            )

    def search_coin(self, query: str) -> Optional[str]:
        """
        Search for a coin and return its slug.

        Args:
            query: Search string (symbol or name)

        Returns:
            Coin slug or None
        """
        data = self._make_request("/coins", params={"search": query, "limit": 10})

        coins = data.get("data", data) if isinstance(data, dict) else data

        if not coins:
            return None

        # Try exact symbol match
        query_upper = query.upper()
        for coin in coins if isinstance(coins, list) else []:
            if coin.get("symbol", "").upper() == query_upper:
                return coin.get("slug") or coin.get("key")

        # Fall back to first result
        if isinstance(coins, list) and coins:
            return coins[0].get("slug") or coins[0].get("key")

        return None

    def get_coin_info(self, slug: str) -> dict[str, Any]:
        """
        Get detailed coin information.

        Args:
            slug: Coin slug (e.g., "jito")

        Returns:
            Coin data dictionary
        """
        return self._make_request(f"/coins/{slug}")

    def get_unlock_schedule(
        self,
        slug: Optional[str] = None,
        symbol: Optional[str] = None,
    ) -> Optional[TokenUnlockSchedule]:
        """
        Get token unlock schedule.

        Args:
            slug: Coin slug
            symbol: Token symbol (will be resolved to slug)

        Returns:
            TokenUnlockSchedule or None
        """
        if slug is None and symbol:
            slug = self.search_coin(symbol)

        if not slug:
            logger.warning(f"Could not resolve slug for {symbol}")
            return None

        cache_key = f"unlocks:{slug}"
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached

        data = self._make_request(f"/unlocks/{slug}")

        if not data:
            return None

        # Parse unlock data
        unlock_data = data.get("data", data)

        upcoming = []
        for event in unlock_data.get("upcomingUnlocks", []):
            try:
                date_str = event.get("date") or event.get("unlockDate")
                if date_str:
                    date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                else:
                    continue

                upcoming.append(TokenUnlockEvent(
                    date=date,
                    amount=float(event.get("amount", 0)),
                    percentage=float(event.get("percentage", 0)),
                    allocation=event.get("allocation", "Unknown"),
                    is_cliff=event.get("isCliff", False),
                ))
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse unlock event: {e}")
                continue

        # Parse allocations
        allocations = {}
        for alloc in unlock_data.get("allocations", []):
            name = alloc.get("name") or alloc.get("category", "Unknown")
            pct = float(alloc.get("percentage", 0))
            allocations[name] = pct

        source_ref = SourceReference(
            source=DataSource.DROPSTAB,
            url=f"https://dropstab.com/coins/{slug}",
            endpoint=f"/unlocks/{slug}",
        )

        result = TokenUnlockSchedule(
            token_symbol=unlock_data.get("symbol", ""),
            token_name=unlock_data.get("name", ""),
            total_supply=float(unlock_data.get("totalSupply", 0)),
            circulating_supply=float(unlock_data.get("circulatingSupply", 0)),
            unlocked_percentage=float(unlock_data.get("unlockedPercentage", 0)),
            upcoming_unlocks=upcoming,
            allocations=allocations,
            source=source_ref,
        )

        self._set_cache(cache_key, result)
        return result

    def get_fundraising(
        self,
        slug: Optional[str] = None,
        symbol: Optional[str] = None,
    ) -> Optional[FundraisingData]:
        """
        Get fundraising data for a token.

        Args:
            slug: Coin slug
            symbol: Token symbol (will be resolved to slug)

        Returns:
            FundraisingData or None
        """
        if slug is None and symbol:
            slug = self.search_coin(symbol)

        if not slug:
            logger.warning(f"Could not resolve slug for {symbol}")
            return None

        cache_key = f"fundraising:{slug}"
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached

        data = self._make_request(f"/funding-rounds/coin/{slug}")

        if not data:
            return None

        rounds_data = data.get("data", data)
        if isinstance(rounds_data, dict):
            rounds_data = rounds_data.get("rounds", [])

        rounds = []
        total_raised = 0.0
        all_investors = set()
        lead_investors = set()

        for round_info in rounds_data if isinstance(rounds_data, list) else []:
            try:
                amount = float(round_info.get("raise") or round_info.get("amount") or 0)
                total_raised += amount

                # Parse date
                date_str = round_info.get("date") or round_info.get("announcedDate")
                round_date = None
                if date_str:
                    try:
                        round_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    except ValueError:
                        pass

                # Parse investors
                round_investors = []
                round_leads = []
                for inv in round_info.get("investors", []):
                    inv_name = inv.get("name", "") if isinstance(inv, dict) else str(inv)
                    if inv_name:
                        round_investors.append(inv_name)
                        all_investors.add(inv_name)
                        if isinstance(inv, dict) and inv.get("isLead"):
                            round_leads.append(inv_name)
                            lead_investors.add(inv_name)

                rounds.append(FundraisingRound(
                    round_name=round_info.get("roundType") or round_info.get("stage", "Unknown"),
                    amount_usd=amount if amount > 0 else None,
                    date=round_date,
                    valuation_usd=round_info.get("valuation"),
                    token_price=round_info.get("tokenPrice"),
                    investors=round_investors,
                    lead_investors=round_leads,
                ))
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse funding round: {e}")
                continue

        source_ref = SourceReference(
            source=DataSource.DROPSTAB,
            url=f"https://dropstab.com/coins/{slug}",
            endpoint=f"/funding-rounds/coin/{slug}",
        )

        result = FundraisingData(
            total_raised_usd=total_raised if total_raised > 0 else None,
            rounds=rounds,
            investors=list(all_investors),
            lead_investors=list(lead_investors),
            source=source_ref,
        )

        self._set_cache(cache_key, result)
        return result

    def get_all_data(
        self,
        slug: Optional[str] = None,
        symbol: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Get all available data for a token.

        Args:
            slug: Coin slug
            symbol: Token symbol

        Returns:
            Dictionary with unlock_schedule and fundraising data
        """
        if slug is None and symbol:
            slug = self.search_coin(symbol)

        if not slug:
            return {"error": f"Could not resolve slug for {symbol}"}

        return {
            "slug": slug,
            "unlock_schedule": self.get_unlock_schedule(slug=slug),
            "fundraising": self.get_fundraising(slug=slug),
        }
