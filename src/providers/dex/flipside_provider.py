#!/usr/bin/env python3
"""
Flipside DEX Data Provider

Provides on-chain DEX swap data from Flipside Crypto.

Two methods available:
1. FlipsideAI MCP (conversational) - for ad-hoc queries
2. Shroomdk API (SQL) - for automated queries (requires separate API key)

For now, this module supports manual data input from FlipsideAI queries.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class DEXSwapData:
    """DEX swap price data for a specific hour."""
    hour: datetime
    swap_program: str
    avg_sell_price: Optional[float]
    avg_buy_price: Optional[float]
    swap_count: int
    source: str = "flipside"


@dataclass
class DEXStabilizationResult:
    """Result of DEX price stabilization analysis."""
    stabilization_hour: datetime
    reference_price: float
    spread_pct: float
    confidence: str  # HIGH, MEDIUM, LOW
    dex_prices: dict[str, float]
    total_swaps: int


# JTO Pre-collected data from FlipsideAI (2023-12-07)
JTO_DEX_DATA = {
    "token_mint": "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL",
    "listing_date": "2023-12-07",
    "first_swap": "2023-12-07 16:04:29",
    "hourly_data": {
        "2023-12-07 16:00": {
            # No price data - high volatility
            "orca_whirlpool": {"swaps": 27791, "avg_buy": None, "avg_sell": None},
            "raydium_clmm": {"swaps": 12467, "avg_buy": None, "avg_sell": None},
            "jupiter_v2": {"swaps": 673, "avg_buy": None, "avg_sell": None},
        },
        "2023-12-07 17:00": {
            # No price data - still volatile
            "orca_whirlpool": {"swaps": 16208, "avg_buy": None, "avg_sell": None},
            "raydium_clmm": {"swaps": 6253, "avg_buy": None, "avg_sell": None},
            "phoenix": {"swaps": 2284, "avg_buy": None, "avg_sell": None},
        },
        "2023-12-07 18:00": {
            # STABILIZATION - prices converge
            "orca_whirlpool": {"swaps": 12154, "avg_buy": 2.0353, "avg_sell": 2.0359},
            "phoenix": {"swaps": 2791, "avg_buy": 2.0356, "avg_sell": 2.0357},
            "raydium_clmm": {"swaps": 2913, "avg_buy": 2.0348, "avg_sell": 2.0326},
            "jupiter_v2": {"swaps": 261, "avg_buy": 2.0190, "avg_sell": 2.0357},
            "meteora_dlmm": {"swaps": 1543, "avg_buy": 2.0349, "avg_sell": 2.0359},
            "meteora_pools": {"swaps": 124, "avg_buy": 2.0346, "avg_sell": 2.0350},
        },
        "2023-12-07 19:00": {
            "orca_whirlpool": {"swaps": 11628, "avg_buy": 2.0263, "avg_sell": 2.0269},
            "phoenix": {"swaps": 2616, "avg_buy": 2.0277, "avg_sell": 2.0277},
            "raydium_clmm": {"swaps": 2069, "avg_buy": 2.0254, "avg_sell": 2.0278},
        },
        "2023-12-07 20:00": {
            "orca_whirlpool": {"swaps": 9720, "avg_buy": 1.8667, "avg_sell": 1.8669},
            "phoenix": {"swaps": 2252, "avg_buy": 1.8667, "avg_sell": 1.8667},
        },
    },
}


def get_jto_stabilization() -> DEXStabilizationResult:
    """
    Get JTO price stabilization data.

    Returns the first hour where DEX prices converge within 1% spread.
    """
    hour_18 = JTO_DEX_DATA["hourly_data"]["2023-12-07 18:00"]

    # Extract prices
    dex_prices = {}
    total_swaps = 0
    prices_list = []

    for dex, data in hour_18.items():
        if data["avg_buy"] is not None:
            avg_price = (data["avg_buy"] + data["avg_sell"]) / 2
            dex_prices[dex] = avg_price
            prices_list.append(avg_price)
            total_swaps += data["swaps"]

    # Calculate spread
    min_price = min(prices_list)
    max_price = max(prices_list)
    spread_pct = ((max_price - min_price) / min_price) * 100

    # Volume-weighted average price
    weighted_sum = 0
    total_weight = 0
    for dex, data in hour_18.items():
        if data["avg_buy"] is not None:
            avg_price = (data["avg_buy"] + data["avg_sell"]) / 2
            weight = data["swaps"]
            weighted_sum += avg_price * weight
            total_weight += weight

    reference_price = weighted_sum / total_weight if total_weight > 0 else 0

    return DEXStabilizationResult(
        stabilization_hour=datetime(2023, 12, 7, 18, 0, 0),
        reference_price=round(reference_price, 4),
        spread_pct=round(spread_pct, 2),
        confidence="HIGH" if spread_pct < 1.0 else "MEDIUM",
        dex_prices=dex_prices,
        total_swaps=total_swaps,
    )


def calculate_benchmark_fdv(
    reference_price: float,
    total_supply: int,
    tge_circulating_pct: float
) -> dict:
    """
    Calculate benchmark FDV and MCap from reference price.
    """
    fdv = total_supply * reference_price
    mcap = total_supply * (tge_circulating_pct / 100) * reference_price

    return {
        "reference_price": reference_price,
        "fdv_usd": fdv,
        "mcap_usd": mcap,
        "total_supply": total_supply,
        "tge_circulating_pct": tge_circulating_pct,
    }


# Example usage
if __name__ == "__main__":
    print("=" * 60)
    print("JTO DEX STABILIZATION ANALYSIS")
    print("=" * 60)

    result = get_jto_stabilization()

    print(f"\nStabilization Hour: {result.stabilization_hour}")
    print(f"Reference Price: ${result.reference_price:.4f}")
    print(f"Spread: {result.spread_pct:.2f}%")
    print(f"Confidence: {result.confidence}")
    print(f"Total Swaps: {result.total_swaps:,}")

    print("\nDEX Prices:")
    for dex, price in result.dex_prices.items():
        print(f"  {dex}: ${price:.4f}")

    print("\n" + "=" * 60)
    print("BENCHMARK VALUATION")
    print("=" * 60)

    valuation = calculate_benchmark_fdv(
        reference_price=result.reference_price,
        total_supply=1_000_000_000,
        tge_circulating_pct=11.5
    )

    print(f"\nReference Price: ${valuation['reference_price']:.4f}")
    print(f"FDV: ${valuation['fdv_usd']:,.0f}")
    print(f"MCap (TGE): ${valuation['mcap_usd']:,.0f}")
