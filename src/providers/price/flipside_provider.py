"""Flipside Crypto provider for DEX price data.

This provider fetches DEX swap data from Flipside's data warehouse
to determine stabilization prices after token launches.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from ...core.models import SourceReference
from ...core.types import ConfidenceLevel, DataSource
from ..base import BaseProvider

logger = logging.getLogger(__name__)


@dataclass
class DexHourlyPrice:
    """Hourly price data from a DEX."""

    hour: datetime
    dex_program: str
    avg_sell_price: float | None
    avg_buy_price: float | None
    swap_count: int
    volume_usd: float | None = None


@dataclass
class StabilizationResult:
    """Result of DEX price stabilization detection."""

    stabilization_hour: datetime
    reference_price: float
    spread_pct: float
    confidence: ConfidenceLevel
    dex_prices: dict[str, float]  # dex_program -> price
    total_swaps: int
    method: str = "dex_convergence"


class FlipsideProvider(BaseProvider):
    """Provider for Flipside Crypto DEX data.

    This provider is designed to work with the Flipside MCP tools.
    It generates SQL queries that can be executed via mcp__flipside-crypto__run_sql_query.
    """

    SOURCE = DataSource.FLIPSIDE

    # Supported blockchains and their DEX tables
    BLOCKCHAIN_TABLES = {
        "solana": "solana.defi.ez_dex_swaps",
        "ethereum": "ethereum.defi.ez_dex_swaps",
        "arbitrum": "arbitrum.defi.ez_dex_swaps",
        "base": "base.defi.ez_dex_swaps",
        "bsc": "bsc.defi.ez_dex_swaps",
        "avalanche": "avalanche.defi.ez_dex_swaps",
    }

    # Stablecoin mints for Solana (used as quote currency)
    SOLANA_STABLECOINS = {
        "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    }

    def __init__(self, **kwargs: Any):
        super().__init__(rate_limit_calls=10, rate_limit_period=60, **kwargs)

    def is_available(self) -> bool:
        """Check if Flipside MCP is available."""
        # This would be checked by attempting a simple query
        # In practice, availability depends on MCP being configured
        return True

    def build_solana_dex_query(
        self,
        token_mint: str,
        start_date: str,
        end_date: str,
        hours_window: int = 24,
    ) -> str:
        """Build SQL query for Solana DEX hourly prices.

        Args:
            token_mint: Solana token mint address
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            hours_window: Number of hours to fetch (default 24)

        Returns:
            SQL query string for Flipside
        """
        query = f"""
SELECT
    DATE_TRUNC('hour', block_timestamp) AS hour,
    swap_program,
    MIN(block_timestamp) AS first_swap,
    COUNT(*) AS swap_count,
    SUM(swap_from_amount_usd) AS volume_usd,
    -- Sell price: token -> stablecoin (from_amount / to_amount when selling token)
    AVG(CASE
        WHEN swap_from_mint = '{token_mint}'
        AND swap_to_mint IN ('{self.SOLANA_STABLECOINS["USDC"]}', '{self.SOLANA_STABLECOINS["USDT"]}')
        THEN swap_to_amount / NULLIF(swap_from_amount, 0)
        END) AS avg_sell_price,
    -- Buy price: stablecoin -> token (from_amount / to_amount when buying token)
    AVG(CASE
        WHEN swap_to_mint = '{token_mint}'
        AND swap_from_mint IN ('{self.SOLANA_STABLECOINS["USDC"]}', '{self.SOLANA_STABLECOINS["USDT"]}')
        THEN swap_from_amount / NULLIF(swap_to_amount, 0)
        END) AS avg_buy_price
FROM solana.defi.ez_dex_swaps
WHERE block_timestamp >= '{start_date}'
    AND block_timestamp < '{end_date}'
    AND (swap_from_mint = '{token_mint}' OR swap_to_mint = '{token_mint}')
GROUP BY 1, 2
HAVING swap_count >= 5
ORDER BY 1, 2
"""
        return query.strip()

    def build_ethereum_dex_query(
        self,
        token_address: str,
        start_date: str,
        end_date: str,
    ) -> str:
        """Build SQL query for Ethereum DEX hourly prices.

        Args:
            token_address: Ethereum token contract address
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            SQL query string for Flipside
        """
        # Common Ethereum stablecoins
        usdc = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
        usdt = "0xdac17f958d2ee523a2206206994597c13d831ec7"

        query = f"""
SELECT
    DATE_TRUNC('hour', block_timestamp) AS hour,
    platform AS swap_program,
    MIN(block_timestamp) AS first_swap,
    COUNT(*) AS swap_count,
    SUM(amount_in_usd) AS volume_usd,
    -- Sell price: token -> stablecoin
    AVG(CASE
        WHEN LOWER(token_in) = LOWER('{token_address}')
        AND LOWER(token_out) IN (LOWER('{usdc}'), LOWER('{usdt}'))
        THEN amount_out / NULLIF(amount_in, 0)
        END) AS avg_sell_price,
    -- Buy price: stablecoin -> token
    AVG(CASE
        WHEN LOWER(token_out) = LOWER('{token_address}')
        AND LOWER(token_in) IN (LOWER('{usdc}'), LOWER('{usdt}'))
        THEN amount_in / NULLIF(amount_out, 0)
        END) AS avg_buy_price
FROM ethereum.defi.ez_dex_swaps
WHERE block_timestamp >= '{start_date}'
    AND block_timestamp < '{end_date}'
    AND (LOWER(token_in) = LOWER('{token_address}') OR LOWER(token_out) = LOWER('{token_address}'))
GROUP BY 1, 2
HAVING swap_count >= 5
ORDER BY 1, 2
"""
        return query.strip()

    def parse_dex_results(self, rows: list[dict]) -> list[DexHourlyPrice]:
        """Parse Flipside query results into DexHourlyPrice objects.

        Args:
            rows: List of row dictionaries from Flipside query

        Returns:
            List of DexHourlyPrice objects
        """
        results = []
        for row in rows:
            # Handle different column name cases (Snowflake returns uppercase)
            hour_val = row.get("HOUR") or row.get("hour")
            if isinstance(hour_val, str):
                hour = datetime.fromisoformat(hour_val.replace("Z", "+00:00"))
            else:
                hour = hour_val

            results.append(DexHourlyPrice(
                hour=hour,
                dex_program=row.get("SWAP_PROGRAM") or row.get("swap_program") or "unknown",
                avg_sell_price=row.get("AVG_SELL_PRICE") or row.get("avg_sell_price"),
                avg_buy_price=row.get("AVG_BUY_PRICE") or row.get("avg_buy_price"),
                swap_count=int(row.get("SWAP_COUNT") or row.get("swap_count") or 0),
                volume_usd=row.get("VOLUME_USD") or row.get("volume_usd"),
            ))
        return results

    def detect_stabilization(
        self,
        hourly_prices: list[DexHourlyPrice],
        spread_threshold_pct: float = 1.0,
        min_dex_count: int = 2,
        min_swaps_per_dex: int = 10,
    ) -> StabilizationResult | None:
        """Detect price stabilization across DEXes.

        Stabilization is detected when multiple DEXes show prices
        within the spread threshold of each other.

        Args:
            hourly_prices: List of hourly DEX prices
            spread_threshold_pct: Maximum spread between DEXes (default 1%)
            min_dex_count: Minimum number of DEXes required (default 2)
            min_swaps_per_dex: Minimum swaps per DEX to consider (default 10)

        Returns:
            StabilizationResult if stabilization detected, None otherwise
        """
        # Group by hour
        by_hour: dict[datetime, list[DexHourlyPrice]] = {}
        for price in hourly_prices:
            if price.hour not in by_hour:
                by_hour[price.hour] = []
            by_hour[price.hour].append(price)

        # Find first hour with price convergence
        for hour in sorted(by_hour.keys()):
            hour_data = by_hour[hour]

            # Get valid prices (prefer sell price, fallback to buy)
            valid_prices: dict[str, float] = {}
            total_swaps = 0

            for dp in hour_data:
                if dp.swap_count < min_swaps_per_dex:
                    continue

                price = dp.avg_sell_price or dp.avg_buy_price
                if price and price > 0:
                    valid_prices[dp.dex_program] = price
                    total_swaps += dp.swap_count

            # Check if enough DEXes
            if len(valid_prices) < min_dex_count:
                continue

            # Calculate spread
            prices = list(valid_prices.values())
            min_price = min(prices)
            max_price = max(prices)
            spread_pct = ((max_price - min_price) / min_price) * 100

            # Check if within threshold
            if spread_pct <= spread_threshold_pct:
                # Calculate reference price (volume-weighted average would be ideal)
                reference_price = sum(prices) / len(prices)

                # Determine confidence
                if len(valid_prices) >= 4 and spread_pct <= 0.5:
                    confidence = ConfidenceLevel.HIGH
                elif len(valid_prices) >= 3 and spread_pct <= 1.0:
                    confidence = ConfidenceLevel.MEDIUM
                else:
                    confidence = ConfidenceLevel.LOW

                return StabilizationResult(
                    stabilization_hour=hour,
                    reference_price=round(reference_price, 6),
                    spread_pct=round(spread_pct, 2),
                    confidence=confidence,
                    dex_prices=valid_prices,
                    total_swaps=total_swaps,
                )

        return None

    def get_source_reference(self, query: str) -> SourceReference:
        """Create a source reference for audit trail."""
        return SourceReference(
            source=self.SOURCE,
            endpoint="mcp__flipside-crypto__run_sql_query",
            url="https://flipsidecrypto.xyz",
            timestamp=datetime.utcnow(),
        )


# Utility functions for direct MCP usage

def build_tge_price_query(
    token_mint: str,
    blockchain: str,
    tge_date: str,
    hours_after: int = 24,
) -> str:
    """Build a query for TGE day prices.

    This is a convenience function for common use case.

    Args:
        token_mint: Token mint/contract address
        blockchain: Blockchain name (solana, ethereum, etc.)
        tge_date: TGE date in YYYY-MM-DD format
        hours_after: Hours after TGE to fetch (default 24)

    Returns:
        SQL query string
    """
    provider = FlipsideProvider()

    # Calculate end date
    start = datetime.strptime(tge_date, "%Y-%m-%d")
    end = start + timedelta(days=2)  # Fetch 2 days to be safe
    end_date = end.strftime("%Y-%m-%d")

    if blockchain.lower() == "solana":
        return provider.build_solana_dex_query(
            token_mint=token_mint,
            start_date=tge_date,
            end_date=end_date,
        )
    elif blockchain.lower() == "ethereum":
        return provider.build_ethereum_dex_query(
            token_address=token_mint,
            start_date=tge_date,
            end_date=end_date,
        )
    else:
        raise ValueError(f"Unsupported blockchain: {blockchain}")
