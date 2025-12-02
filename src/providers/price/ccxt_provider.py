"""CCXT-based price provider for fetching exchange candle data.

This provider uses the CCXT library to fetch historical OHLCV data
from multiple cryptocurrency exchanges to find the earliest listing candle.
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import ccxt

from ...core.exceptions import DataSourceError
from ...core.models import ExchangeCandle, ExchangeListing, SourceReference
from ...core.types import DataSource, TimeframeType
from ..base import CachedProvider

logger = logging.getLogger(__name__)


# Exchange priority and configuration
DEFAULT_EXCHANGES = [
    "binance",
    "okx",
    "bybit",
    "kucoin",
    "gateio",
    "htx",
    "coinbase",
    "kraken",
]

QUOTE_CURRENCIES = ["USDT", "USDC", "USD", "BUSD", "BTC", "ETH"]


class CCXTPriceProvider(CachedProvider):
    """Fetches initial listing prices from exchanges via CCXT."""

    SOURCE = DataSource.CCXT

    def __init__(
        self,
        exchanges: list[str] | None = None,
        rate_limit_calls: int = 30,
        rate_limit_period: int = 60,
        cache_ttl_seconds: int = 86400,  # 24 hours for historical data
    ):
        """
        Initialize CCXT provider.

        Args:
            exchanges: List of exchange IDs to check (default: major exchanges)
            rate_limit_calls: Rate limit per period
            rate_limit_period: Period in seconds
            cache_ttl_seconds: Cache TTL
        """
        super().__init__(
            rate_limit_calls=rate_limit_calls,
            rate_limit_period=rate_limit_period,
            cache_ttl_seconds=cache_ttl_seconds,
        )
        self.exchange_ids = exchanges or DEFAULT_EXCHANGES
        self._exchange_instances: dict[str, ccxt.Exchange] = {}

    def _get_exchange(self, exchange_id: str) -> ccxt.Exchange | None:
        """Get or create exchange instance."""
        if exchange_id not in self._exchange_instances:
            try:
                exchange_class = getattr(ccxt, exchange_id)
                self._exchange_instances[exchange_id] = exchange_class(
                    {
                        "enableRateLimit": True,
                        "timeout": 30000,
                    }
                )
            except AttributeError:
                logger.warning(f"Exchange not supported by CCXT: {exchange_id}")
                return None
            except Exception as e:
                logger.warning(f"Failed to initialize {exchange_id}: {e}")
                return None
        return self._exchange_instances[exchange_id]

    def is_available(self) -> bool:
        """Check if at least one exchange is available."""
        for exchange_id in self.exchange_ids:
            exchange = self._get_exchange(exchange_id)
            if exchange:
                return True
        return False

    def _find_trading_pair(
        self,
        exchange: ccxt.Exchange,
        base_symbol: str,
    ) -> str | None:
        """
        Find a valid trading pair for the symbol on the exchange.

        Args:
            exchange: CCXT exchange instance
            base_symbol: Base currency symbol (e.g., "ARB")

        Returns:
            Trading pair symbol (e.g., "ARB/USDT") or None
        """
        try:
            exchange.load_markets()
        except Exception as e:
            logger.warning(f"Failed to load markets for {exchange.id}: {e}")
            return None

        base_symbol = base_symbol.upper()

        # Try each quote currency in order of preference
        for quote in QUOTE_CURRENCIES:
            pair = f"{base_symbol}/{quote}"
            if pair in exchange.markets:
                return pair

        # Check if any pair exists with this base
        for symbol in exchange.markets:
            if symbol.startswith(f"{base_symbol}/"):
                return symbol

        return None

    def _fetch_earliest_candles(
        self,
        exchange: ccxt.Exchange,
        symbol: str,
        timeframe: TimeframeType = "1h",
        since_hint: datetime | None = None,
        lookback_days: int = 7,
    ) -> list[list[Any]]:
        """
        Fetch the earliest available candles for a symbol.

        Uses binary search approach: start from hint date, if data exists,
        go earlier; if not, go later.

        Args:
            exchange: CCXT exchange instance
            symbol: Trading pair symbol
            timeframe: Candle timeframe
            since_hint: Optional date hint for when listing occurred
            lookback_days: Days to look back from hint

        Returns:
            List of OHLCV candles [[timestamp, o, h, l, c, v], ...]
        """
        self._wait_for_rate_limit()

        # Determine search start point
        if since_hint:
            search_start = since_hint - timedelta(days=lookback_days)
        else:
            # Default: search from 2 years ago
            search_start = datetime.now(timezone.utc) - timedelta(days=730)

        since_ms = int(search_start.timestamp() * 1000)

        try:
            # Fetch candles
            candles = exchange.fetch_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                since=since_ms,
                limit=500,  # Get enough to find the earliest
            )
            return candles or []

        except ccxt.BadSymbol:
            logger.debug(f"{exchange.id}: Symbol {symbol} not found")
            return []
        except ccxt.ExchangeNotAvailable as e:
            logger.warning(f"{exchange.id} not available: {e}")
            return []
        except Exception as e:
            logger.warning(f"{exchange.id} fetch error for {symbol}: {e}")
            return []

    def get_listing_for_exchange(
        self,
        exchange_id: str,
        symbol: str,
        timeframe: TimeframeType = "1h",
        since_hint: datetime | None = None,
    ) -> ExchangeListing:
        """
        Get listing data from a specific exchange.

        Args:
            exchange_id: CCXT exchange ID
            symbol: Token symbol (e.g., "ARB")
            timeframe: Candle timeframe
            since_hint: Optional listing date hint

        Returns:
            ExchangeListing with first candle data or error
        """
        start_time = time.time()
        exchange = self._get_exchange(exchange_id)

        if not exchange:
            return ExchangeListing(
                exchange=exchange_id,
                trading_pair="",
                base_currency=symbol,
                quote_currency="",
                error=f"Exchange {exchange_id} not available",
            )

        # Find trading pair
        pair = self._find_trading_pair(exchange, symbol)
        if not pair:
            self._record_audit(
                action="fetch",
                endpoint=f"{exchange_id}/markets",
                success=False,
                error_message=f"No trading pair found for {symbol}",
                duration_ms=int((time.time() - start_time) * 1000),
            )
            return ExchangeListing(
                exchange=exchange_id,
                trading_pair="",
                base_currency=symbol,
                quote_currency="",
                error=f"No trading pair found for {symbol}",
            )

        base, quote = pair.split("/")

        # Check cache
        cache_key = f"{exchange_id}:{pair}:{timeframe}"
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        # Fetch candles
        candles = self._fetch_earliest_candles(
            exchange=exchange,
            symbol=pair,
            timeframe=timeframe,
            since_hint=since_hint,
        )

        duration_ms = int((time.time() - start_time) * 1000)

        if not candles:
            self._record_audit(
                action="fetch",
                endpoint=f"{exchange_id}/ohlcv/{pair}",
                success=False,
                error_message="No candle data available",
                duration_ms=duration_ms,
            )
            return ExchangeListing(
                exchange=exchange_id,
                trading_pair=pair,
                base_currency=base,
                quote_currency=quote,
                timeframe=timeframe,
                error="No candle data available",
            )

        # Parse first candle
        first_candle_data = candles[0]
        first_candle = ExchangeCandle(
            timestamp=datetime.fromtimestamp(first_candle_data[0] / 1000, tz=timezone.utc),
            open=float(first_candle_data[1]),
            high=float(first_candle_data[2]),
            low=float(first_candle_data[3]),
            close=float(first_candle_data[4]),
            volume=float(first_candle_data[5]),
        )

        source_ref = SourceReference(
            source=DataSource.CCXT,
            endpoint=f"{exchange_id}/ohlcv/{pair}/{timeframe}",
        )

        self._record_audit(
            action="fetch",
            endpoint=f"{exchange_id}/ohlcv/{pair}",
            success=True,
            duration_ms=duration_ms,
            notes=f"First candle: {first_candle.timestamp.isoformat()}",
        )

        result = ExchangeListing(
            exchange=exchange_id,
            trading_pair=pair,
            base_currency=base,
            quote_currency=quote,
            first_candle=first_candle,
            timeframe=timeframe,
            source=source_ref,
        )

        self._set_cache(cache_key, result)
        return result

    def get_listings_all_exchanges(
        self,
        symbol: str,
        timeframe: TimeframeType = "1h",
        since_hint: datetime | None = None,
    ) -> list[ExchangeListing]:
        """
        Get listing data from all configured exchanges.

        Args:
            symbol: Token symbol (e.g., "ARB")
            timeframe: Candle timeframe
            since_hint: Optional listing date hint

        Returns:
            List of ExchangeListing objects, one per exchange attempted
        """
        logger.info(f"Fetching listings for {symbol} from {len(self.exchange_ids)} exchanges")

        listings = []
        for exchange_id in self.exchange_ids:
            listing = self.get_listing_for_exchange(
                exchange_id=exchange_id,
                symbol=symbol,
                timeframe=timeframe,
                since_hint=since_hint,
            )
            listings.append(listing)

            if listing.has_data:
                logger.info(
                    f"  {exchange_id}: {listing.trading_pair} "
                    f"first candle {listing.first_candle.timestamp}"
                )
            else:
                logger.debug(f"  {exchange_id}: {listing.error or 'No data'}")

        return listings

    def find_earliest_listing(
        self,
        symbol: str,
        timeframe: TimeframeType = "1h",
        since_hint: datetime | None = None,
    ) -> ExchangeListing | None:
        """
        Find the earliest listing across all exchanges.

        Args:
            symbol: Token symbol
            timeframe: Candle timeframe
            since_hint: Optional listing date hint

        Returns:
            ExchangeListing with the earliest first_candle, or None
        """
        listings = self.get_listings_all_exchanges(symbol, timeframe, since_hint)

        # Filter to successful listings
        valid_listings = [l for l in listings if l.has_data and l.first_candle]

        if not valid_listings:
            return None

        # Sort by first candle timestamp
        valid_listings.sort(key=lambda l: l.first_candle.timestamp)

        earliest = valid_listings[0]
        logger.info(
            f"Earliest listing: {earliest.exchange} at "
            f"{earliest.first_candle.timestamp}"
        )

        return earliest
