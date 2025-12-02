"""Price selector - chooses the reference initial price from multiple sources.

When we have listing data from multiple exchanges, this module
implements the logic to select the most appropriate reference price.
"""

import logging
from datetime import datetime, timedelta, timezone

from ..core.models import ExchangeCandle, ExchangeListing, ReferencePrice
from ..core.types import ConfidenceLevel, PriceSelectionMethod

logger = logging.getLogger(__name__)


# Exchange reliability ranking (higher = more reliable)
EXCHANGE_RELIABILITY = {
    "binance": 100,
    "coinbase": 95,
    "okx": 90,
    "kraken": 90,
    "bybit": 85,
    "kucoin": 80,
    "gateio": 75,
    "htx": 70,
    "coingecko": 50,  # Aggregator, daily data
}


class PriceSelector:
    """Selects the reference initial price from multiple exchange listings."""

    def __init__(
        self,
        method: PriceSelectionMethod = PriceSelectionMethod.EARLIEST_OPEN,
        min_volume_usd: float = 1000.0,
        max_price_deviation_pct: float = 50.0,
        prefer_stablecoin_pairs: bool = True,
    ):
        """
        Initialize price selector.

        Args:
            method: Default selection method
            min_volume_usd: Minimum volume to consider candle valid
            max_price_deviation_pct: Max deviation from median to filter outliers
            prefer_stablecoin_pairs: Prefer USDT/USDC pairs over BTC/ETH
        """
        self.method = method
        self.min_volume_usd = min_volume_usd
        self.max_price_deviation_pct = max_price_deviation_pct
        self.prefer_stablecoin_pairs = prefer_stablecoin_pairs

    def _is_stablecoin_pair(self, pair: str) -> bool:
        """Check if trading pair uses a stablecoin quote."""
        quote = pair.split("/")[-1].upper() if "/" in pair else ""
        return quote in ("USDT", "USDC", "USD", "BUSD", "DAI", "TUSD")

    def _filter_valid_listings(
        self,
        listings: list[ExchangeListing],
    ) -> list[ExchangeListing]:
        """Filter to listings with valid candle data."""
        valid = []

        for listing in listings:
            if not listing.has_data or not listing.first_candle:
                continue

            candle = listing.first_candle

            # Check candle validity
            if not candle.is_valid:
                logger.debug(f"Skipping {listing.exchange}: invalid candle data")
                continue

            # Check minimum volume (if we have volume data)
            if candle.volume_usd and candle.volume_usd < self.min_volume_usd:
                logger.debug(
                    f"Skipping {listing.exchange}: volume ${candle.volume_usd:.0f} "
                    f"< min ${self.min_volume_usd:.0f}"
                )
                continue

            valid.append(listing)

        return valid

    def _filter_outliers(
        self,
        listings: list[ExchangeListing],
    ) -> list[ExchangeListing]:
        """Filter out price outliers based on deviation from median."""
        if len(listings) < 3:
            return listings

        # Get prices
        prices = [l.first_candle.open for l in listings if l.first_candle]

        if not prices:
            return listings

        # Calculate median
        sorted_prices = sorted(prices)
        mid = len(sorted_prices) // 2
        if len(sorted_prices) % 2 == 0:
            median = (sorted_prices[mid - 1] + sorted_prices[mid]) / 2
        else:
            median = sorted_prices[mid]

        # Filter based on deviation
        filtered = []
        for listing in listings:
            if not listing.first_candle:
                continue

            price = listing.first_candle.open
            deviation_pct = abs(price - median) / median * 100

            if deviation_pct <= self.max_price_deviation_pct:
                filtered.append(listing)
            else:
                logger.warning(
                    f"Excluding {listing.exchange} as outlier: "
                    f"${price:.6f} is {deviation_pct:.1f}% from median ${median:.6f}"
                )

        return filtered if filtered else listings

    def _get_exchange_reliability(self, exchange: str) -> int:
        """Get reliability score for an exchange."""
        return EXCHANGE_RELIABILITY.get(exchange.lower(), 50)

    def _get_price_from_candle(
        self,
        candle: ExchangeCandle,
        method: PriceSelectionMethod,
    ) -> float:
        """Extract price from candle based on method."""
        if method == PriceSelectionMethod.EARLIEST_OPEN:
            return candle.open
        elif method == PriceSelectionMethod.EARLIEST_CLOSE:
            return candle.close
        elif method in (PriceSelectionMethod.FIRST_HOUR_VWAP, PriceSelectionMethod.FIRST_DAY_VWAP):
            # For VWAP, we'd need more candles - use average of OHLC as approximation
            return (candle.open + candle.high + candle.low + candle.close) / 4
        else:
            return candle.open

    def select(
        self,
        listings: list[ExchangeListing],
        method: PriceSelectionMethod | None = None,
    ) -> ReferencePrice | None:
        """
        Select the reference initial price from multiple listings.

        Selection logic:
        1. Filter to valid listings with candle data
        2. Filter out price outliers
        3. Find earliest listing
        4. If multiple have same timestamp, prefer reliable exchanges
        5. If tie, prefer stablecoin pairs

        Args:
            listings: List of ExchangeListing objects
            method: Override selection method

        Returns:
            ReferencePrice or None if no valid listings
        """
        method = method or self.method

        # Filter valid listings
        valid_listings = self._filter_valid_listings(listings)

        if not valid_listings:
            logger.warning("No valid listings found for price selection")
            return None

        logger.info(f"Price selection: {len(valid_listings)} valid listings from {len(listings)} total")

        # Filter outliers
        filtered_listings = self._filter_outliers(valid_listings)

        # Sort by timestamp (earliest first)
        filtered_listings.sort(key=lambda x: x.first_candle.timestamp)

        # Get earliest timestamp
        earliest_ts = filtered_listings[0].first_candle.timestamp

        # Find all listings within 1 hour of earliest (might be same launch on multiple exchanges)
        candidates = [
            l for l in filtered_listings
            if l.first_candle.timestamp <= earliest_ts + timedelta(hours=1)
        ]

        if len(candidates) > 1:
            # Multiple candidates - rank by preference
            def ranking_key(listing: ExchangeListing) -> tuple:
                reliability = -self._get_exchange_reliability(listing.exchange)
                is_stablecoin = -1 if self._is_stablecoin_pair(listing.trading_pair) else 0
                timestamp = listing.first_candle.timestamp.timestamp()
                return (timestamp, is_stablecoin, reliability)

            candidates.sort(key=ranking_key)

        # Select best candidate
        selected = candidates[0]
        candle = selected.first_candle

        price = self._get_price_from_candle(candle, method)

        # Determine confidence
        confidence = ConfidenceLevel.MEDIUM
        if len(valid_listings) >= 3:
            # Multiple sources agree
            prices = [l.first_candle.open for l in valid_listings[:5]]
            avg_price = sum(prices) / len(prices)
            deviation = abs(price - avg_price) / avg_price * 100
            if deviation < 5:
                confidence = ConfidenceLevel.HIGH
        elif self._get_exchange_reliability(selected.exchange) >= 90:
            confidence = ConfidenceLevel.HIGH

        # Build notes
        notes_parts = [
            f"Selected from {len(valid_listings)} valid listings",
            f"Earliest listing: {selected.exchange}",
        ]
        if len(candidates) > 1:
            notes_parts.append(
                f"Tied with {len(candidates)-1} other exchange(s) within 1h"
            )

        return ReferencePrice(
            price_usd=price,
            timestamp=candle.timestamp,
            method=method,
            source_exchange=selected.exchange,
            source_pair=selected.trading_pair,
            confidence=confidence,
            notes="; ".join(notes_parts),
        )

    def select_with_fallback(
        self,
        exchange_listings: list[ExchangeListing],
        coingecko_listing: ExchangeListing | None = None,
        method: PriceSelectionMethod | None = None,
    ) -> ReferencePrice | None:
        """
        Select price with CoinGecko fallback if no exchange data.

        Args:
            exchange_listings: Listings from exchanges via CCXT
            coingecko_listing: Optional fallback from CoinGecko historical data
            method: Override selection method

        Returns:
            ReferencePrice or None
        """
        # Try exchange data first
        result = self.select(exchange_listings, method)

        if result:
            return result

        # Fall back to CoinGecko
        if coingecko_listing and coingecko_listing.has_data:
            logger.info("Using CoinGecko historical data as fallback")
            candle = coingecko_listing.first_candle
            price = self._get_price_from_candle(candle, method or self.method)

            return ReferencePrice(
                price_usd=price,
                timestamp=candle.timestamp,
                method=method or self.method,
                source_exchange="coingecko",
                source_pair=coingecko_listing.trading_pair,
                confidence=ConfidenceLevel.LOW,
                notes="Fallback to CoinGecko daily data; exchange data unavailable",
            )

        return None

    def create_manual_price(
        self,
        price_usd: float,
        timestamp: datetime | None = None,
        notes: str | None = None,
    ) -> ReferencePrice:
        """
        Create a manually specified reference price.

        Args:
            price_usd: The price in USD
            timestamp: Optional timestamp (defaults to now)
            notes: Optional notes about the source

        Returns:
            ReferencePrice with MANUAL method
        """
        return ReferencePrice(
            price_usd=price_usd,
            timestamp=timestamp or datetime.now(timezone.utc),
            method=PriceSelectionMethod.MANUAL,
            source_exchange="manual",
            source_pair="MANUAL/USD",
            confidence=ConfidenceLevel.HIGH,
            notes=notes or "Manually specified by analyst",
        )
