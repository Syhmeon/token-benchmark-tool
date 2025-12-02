"""Flipside SQL API Provider for DEX on-chain data.

Uses the Flipside Crypto API to query on-chain DEX swap data
for price stabilization analysis.

API Documentation: https://docs.flipsidecrypto.xyz/
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx

from ...core.config import get_config
from ...core.exceptions import DataSourceError, RateLimitError
from ...core.models import SourceReference
from ...core.types import DataSource
from ..base import CachedProvider

logger = logging.getLogger(__name__)


@dataclass
class DEXSwapData:
    """DEX swap price data for a specific hour."""
    hour: datetime
    swap_program: str
    avg_price: Optional[float]
    swap_count: int
    volume_usd: Optional[float] = None


@dataclass
class DEXStabilizationResult:
    """Result of DEX price stabilization analysis."""
    stabilization_hour: datetime
    reference_price: float
    spread_pct: float
    confidence: str  # HIGH, MEDIUM, LOW
    dex_prices: dict[str, float]
    total_swaps: int
    source: Optional[SourceReference] = None


class FlipsideSQLProvider(CachedProvider):
    """Fetches DEX swap data from Flipside Crypto SQL API."""

    SOURCE = DataSource.FLIPSIDE
    BASE_URL = "https://api-v2.flipsidecrypto.xyz"

    # Solana DEX swap query template
    SOLANA_DEX_QUERY = """
    SELECT
        DATE_TRUNC('hour', block_timestamp) as hour,
        swap_program,
        AVG(
            CASE
                WHEN swap_to_mint = '{token_mint}' THEN swap_from_amount / NULLIF(swap_to_amount, 0)
                WHEN swap_from_mint = '{token_mint}' THEN swap_to_amount / NULLIF(swap_from_amount, 0)
            END
        ) as avg_price,
        COUNT(*) as swap_count,
        SUM(
            CASE
                WHEN swap_to_mint = '{token_mint}' THEN swap_from_amount
                ELSE swap_to_amount
            END
        ) as volume
    FROM solana.defi.fact_swaps
    WHERE (swap_to_mint = '{token_mint}' OR swap_from_mint = '{token_mint}')
        AND block_timestamp >= '{start_date}'
        AND block_timestamp < '{end_date}'
        AND (
            swap_to_mint IN ('EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v', 'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB')
            OR swap_from_mint IN ('EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v', 'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB')
        )
    GROUP BY 1, 2
    HAVING avg_price IS NOT NULL AND avg_price > 0
    ORDER BY 1, swap_count DESC
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        rate_limit_calls: int = 10,
        rate_limit_period: int = 60,
        cache_ttl_seconds: int = 86400,  # 24h for historical data
    ):
        """
        Initialize Flipside SQL provider.

        Args:
            api_key: Flipside API key (loaded from config if not provided)
            rate_limit_calls: Rate limit per period
            rate_limit_period: Period in seconds
            cache_ttl_seconds: Cache TTL
        """
        super().__init__(
            rate_limit_calls=rate_limit_calls,
            rate_limit_period=rate_limit_period,
            cache_ttl_seconds=cache_ttl_seconds,
        )
        self.api_key = api_key or get_config().flipside_api_key

    def is_available(self) -> bool:
        """Check if Flipside API is available and configured."""
        return bool(self.api_key)

    def _run_query(self, sql: str) -> list[dict[str, Any]]:
        """
        Execute a SQL query via Flipside API.

        Args:
            sql: SQL query string

        Returns:
            List of result rows as dictionaries
        """
        if not self.api_key:
            raise DataSourceError(
                source="flipside",
                message="API key not configured",
            )

        self._wait_for_rate_limit()
        start_time = time.time()

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
        }

        # Step 1: Create query run
        create_payload = {
            "jsonrpc": "2.0",
            "method": "createQueryRun",
            "params": [
                {
                    "resultTTLHours": 24,
                    "maxAgeMinutes": 0,
                    "sql": sql,
                    "tags": {"source": "token-benchmark-tool"},
                    "dataSource": "snowflake-default",
                    "dataProvider": "flipside",
                }
            ],
            "id": 1,
        }

        try:
            with httpx.Client(timeout=60.0) as client:
                # Create query
                response = client.post(
                    f"{self.BASE_URL}/json-rpc",
                    json=create_payload,
                    headers=headers,
                )

                if response.status_code == 429:
                    raise RateLimitError(
                        source="flipside",
                        retry_after_seconds=60,
                        endpoint="createQueryRun",
                    )

                response.raise_for_status()
                result = response.json()

                if "error" in result:
                    raise DataSourceError(
                        source="flipside",
                        message=result["error"].get("message", "Unknown error"),
                        endpoint="createQueryRun",
                    )

                query_run_id = result.get("result", {}).get("queryRun", {}).get("id")
                if not query_run_id:
                    raise DataSourceError(
                        source="flipside",
                        message="No query run ID returned",
                        endpoint="createQueryRun",
                    )

                # Step 2: Poll for results
                get_payload = {
                    "jsonrpc": "2.0",
                    "method": "getQueryRunResults",
                    "params": [
                        {
                            "queryRunId": query_run_id,
                            "format": "json",
                            "page": {"number": 1, "size": 10000},
                        }
                    ],
                    "id": 1,
                }

                # Poll until complete (max 5 minutes)
                for _ in range(60):
                    time.sleep(5)

                    response = client.post(
                        f"{self.BASE_URL}/json-rpc",
                        json=get_payload,
                        headers=headers,
                    )
                    response.raise_for_status()
                    result = response.json()

                    if "error" in result:
                        error_msg = result["error"].get("message", "")
                        if "not finished" in error_msg.lower():
                            continue
                        raise DataSourceError(
                            source="flipside",
                            message=error_msg,
                            endpoint="getQueryRunResults",
                        )

                    query_result = result.get("result", {})
                    status = query_result.get("queryRun", {}).get("state")

                    if status == "QUERY_STATE_SUCCESS":
                        rows = query_result.get("rows", [])
                        duration_ms = int((time.time() - start_time) * 1000)

                        self._record_audit(
                            action="query",
                            endpoint="getQueryRunResults",
                            success=True,
                            duration_ms=duration_ms,
                            notes=f"Returned {len(rows)} rows",
                        )

                        return rows

                    elif status in ["QUERY_STATE_FAILED", "QUERY_STATE_CANCELED"]:
                        error = query_result.get("queryRun", {}).get("errorMessage", "Query failed")
                        raise DataSourceError(
                            source="flipside",
                            message=error,
                            endpoint="getQueryRunResults",
                        )

                raise DataSourceError(
                    source="flipside",
                    message="Query timed out after 5 minutes",
                    endpoint="getQueryRunResults",
                )

        except httpx.HTTPStatusError as e:
            raise DataSourceError(
                source="flipside",
                message=f"HTTP {e.response.status_code}",
                endpoint="json-rpc",
                status_code=e.response.status_code,
            )
        except httpx.RequestError as e:
            raise DataSourceError(
                source="flipside",
                message=str(e),
                endpoint="json-rpc",
            )

    def get_dex_swaps_hourly(
        self,
        token_mint: str,
        start_date: datetime,
        end_date: Optional[datetime] = None,
        blockchain: str = "solana",
    ) -> list[DEXSwapData]:
        """
        Get hourly DEX swap data for a token.

        Args:
            token_mint: Token mint address
            start_date: Start of date range
            end_date: End of date range (default: start + 24h)
            blockchain: Blockchain name (currently only solana supported)

        Returns:
            List of DEXSwapData for each hour/program combination
        """
        if end_date is None:
            end_date = start_date + timedelta(days=1)

        cache_key = f"dex_swaps:{blockchain}:{token_mint}:{start_date.date()}"
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached

        if blockchain.lower() != "solana":
            logger.warning(f"Blockchain {blockchain} not yet supported, only Solana")
            return []

        # Format query
        sql = self.SOLANA_DEX_QUERY.format(
            token_mint=token_mint,
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
        )

        rows = self._run_query(sql)

        # Parse results
        results = []
        for row in rows:
            try:
                hour_str = row.get("hour") or row.get("HOUR")
                if isinstance(hour_str, str):
                    hour = datetime.fromisoformat(hour_str.replace("Z", "+00:00"))
                else:
                    hour = hour_str

                results.append(DEXSwapData(
                    hour=hour,
                    swap_program=row.get("swap_program") or row.get("SWAP_PROGRAM", "unknown"),
                    avg_price=float(row.get("avg_price") or row.get("AVG_PRICE") or 0),
                    swap_count=int(row.get("swap_count") or row.get("SWAP_COUNT") or 0),
                    volume_usd=float(row.get("volume") or row.get("VOLUME") or 0),
                ))
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse row: {row}, error: {e}")
                continue

        self._set_cache(cache_key, results)
        return results

    def find_stabilization_hour(
        self,
        token_mint: str,
        listing_date: datetime,
        max_hours: int = 24,
        max_spread_pct: float = 1.0,
        min_dex_count: int = 3,
    ) -> Optional[DEXStabilizationResult]:
        """
        Find the first hour where DEX prices stabilize.

        Stabilization is defined as:
        - At least min_dex_count DEX protocols with price data
        - Spread between min/max price < max_spread_pct

        Args:
            token_mint: Token mint address
            listing_date: Token listing date
            max_hours: Maximum hours to search
            max_spread_pct: Maximum acceptable spread percentage
            min_dex_count: Minimum DEX protocols required

        Returns:
            DEXStabilizationResult if found, None otherwise
        """
        end_date = listing_date + timedelta(hours=max_hours)
        swaps = self.get_dex_swaps_hourly(token_mint, listing_date, end_date)

        if not swaps:
            logger.warning(f"No DEX swap data found for {token_mint}")
            return None

        # Group by hour
        hourly_data: dict[datetime, list[DEXSwapData]] = {}
        for swap in swaps:
            if swap.hour not in hourly_data:
                hourly_data[swap.hour] = []
            hourly_data[swap.hour].append(swap)

        # Find first stable hour
        for hour in sorted(hourly_data.keys()):
            hour_swaps = hourly_data[hour]

            # Filter valid prices
            valid_swaps = [s for s in hour_swaps if s.avg_price and s.avg_price > 0]

            if len(valid_swaps) < min_dex_count:
                continue

            prices = [s.avg_price for s in valid_swaps]
            min_price = min(prices)
            max_price = max(prices)
            spread_pct = ((max_price - min_price) / min_price) * 100

            if spread_pct <= max_spread_pct:
                # Found stable hour - calculate VWAP
                total_volume = sum(s.swap_count for s in valid_swaps)
                vwap = sum(s.avg_price * s.swap_count for s in valid_swaps) / total_volume

                dex_prices = {s.swap_program: round(s.avg_price, 4) for s in valid_swaps}

                confidence = "HIGH" if spread_pct < 0.5 else "MEDIUM" if spread_pct < 1.0 else "LOW"

                source_ref = SourceReference(
                    source=DataSource.FLIPSIDE,
                    url="https://flipsidecrypto.xyz",
                    endpoint=f"solana.defi.fact_swaps/{token_mint}",
                )

                return DEXStabilizationResult(
                    stabilization_hour=hour,
                    reference_price=round(vwap, 4),
                    spread_pct=round(spread_pct, 2),
                    confidence=confidence,
                    dex_prices=dex_prices,
                    total_swaps=total_volume,
                    source=source_ref,
                )

        logger.warning(f"No stabilization found within {max_hours} hours for {token_mint}")
        return None


# Convenience function for backward compatibility
def get_dex_stabilization(
    token_mint: str,
    listing_date: datetime,
    api_key: Optional[str] = None,
) -> Optional[DEXStabilizationResult]:
    """
    Get DEX price stabilization data for a token.

    Args:
        token_mint: Token mint address
        listing_date: Token listing date
        api_key: Optional Flipside API key

    Returns:
        DEXStabilizationResult or None
    """
    provider = FlipsideSQLProvider(api_key=api_key)

    if not provider.is_available():
        logger.error("Flipside API key not configured")
        return None

    return provider.find_stabilization_hour(token_mint, listing_date)
