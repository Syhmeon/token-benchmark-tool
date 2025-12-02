#!/usr/bin/env python3
"""Update JTO benchmark with complete allocation data."""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.storage.json_store import (
    BenchmarkStore,
    TokenBenchmark,
    CEXData,
    DEXStabilization,
    FundraisingRound,
    TokenAllocation,
)

def main():
    store = BenchmarkStore()

    # Create complete JTO benchmark
    jto = TokenBenchmark(
        symbol="JTO",
        name="Jito",
        coingecko_id="jito-governance-token",
        blockchain="Solana",
        categories=["Liquid Staking", "MEV Infrastructure", "DeFi"],
        listing_date="2023-12-07",

        # Supply
        total_supply=1_000_000_000,
        max_supply=1_000_000_000,
        tge_circulating_pct=11.5,
        tge_circulating_tokens=115_000_000,
        current_circulating_tokens=456_885_753,

        # Benchmark
        benchmark_price=2.0352,
        benchmark_method="dex_stabilization",
        benchmark_confidence="HIGH",
        fdv_usd=2_035_200_000,
        mcap_usd=234_048_000,

        # CEX Data
        cex_data=[
            CEXData(
                exchange="bybit",
                first_candle_time="2023-12-07 16:00:00 UTC",
                open=0.03,
                high=3.00001,
                low=0.03,
                close=3.0,
                hl_ratio=100.0,
                is_tge_candle=True,
                flag="SUSPECT - extreme wicks",
                vwap_1h=2.1238,
                median_close_1h=2.0535,
            ),
            CEXData(
                exchange="binance",
                first_candle_time="2023-12-07 16:30:00 UTC",
                open=0.15,
                high=4.94,
                low=0.15,
                close=3.6953,
                hl_ratio=32.9,
                is_tge_candle=True,
                flag="30min delay from TGE",
                vwap_1h=2.3149,
                median_close_1h=2.1283,
            ),
        ],

        # DEX Stabilization
        dex_stabilization=DEXStabilization(
            stabilization_hour="2023-12-07T18:00:00",
            reference_price=2.0352,
            spread_pct=0.41,
            confidence="HIGH",
            dex_prices={
                "orca_whirlpool": 2.0356,
                "phoenix": 2.0357,
                "raydium_clmm": 2.0337,
                "jupiter_v2": 2.0274,
                "meteora_dlmm": 2.0354,
                "meteora_pools": 2.0348,
            },
            total_swaps=19786,
        ),

        # Fundraising
        total_raised=12_100_000,
        fundraising_rounds=[
            FundraisingRound(
                name="Seed",
                date="2021-12",
                amount=2_100_000,
                valuation=None,
                lead_investors=["Multicoin Capital"],
                token_price=None,
            ),
            FundraisingRound(
                name="Series A",
                date="2022-08",
                amount=10_000_000,
                valuation=None,
                lead_investors=["Multicoin Capital", "Framework Ventures"],
                token_price=None,
            ),
        ],
        fdv_to_raised_ratio=168.2,

        # Investors
        investors=[
            "Multicoin Capital",
            "Framework Ventures",
            "Solana Ventures",
            "Alameda Research",
            "Jump Crypto",
            "Sino Global Capital",
            "Delphi Digital",
        ],

        # Allocations
        allocations=[
            TokenAllocation(
                bucket="Airdrop",
                percentage=10.0,
                tokens=100_000_000,
                vesting="TGE 100%",
                tge_unlock_pct=100.0,
            ),
            TokenAllocation(
                bucket="Community Growth",
                percentage=24.3,
                tokens=243_000_000,
                vesting="Gradual distribution over 4 years",
                tge_unlock_pct=0.0,
            ),
            TokenAllocation(
                bucket="Ecosystem Development",
                percentage=25.0,
                tokens=250_000_000,
                vesting="Gradual distribution for protocol development",
                tge_unlock_pct=1.5,
            ),
            TokenAllocation(
                bucket="Core Contributors",
                percentage=24.5,
                tokens=245_000_000,
                vesting="3 years, 1 year cliff, monthly thereafter",
                tge_unlock_pct=0.0,
            ),
            TokenAllocation(
                bucket="Investors",
                percentage=16.2,
                tokens=162_000_000,
                vesting="3 years, 1 year cliff, monthly thereafter",
                tge_unlock_pct=0.0,
            ),
        ],

        # Metadata
        methodology_notes=[
            "CEX first candles show H/L ratio > 30x - flagged as TGE candles",
            "Bybit shows impossible wicks ($32) vs ATH ($5.91) - marked SUSPECT",
            "DEX stabilization at +2h when 6 protocols converge within 0.41% spread",
            "Benchmark price = volume-weighted average of DEX prices at stabilization",
        ],
        sources=[
            "CCXT (Bybit, Binance)",
            "Flipside (Solana DEX)",
            "CoinGecko (metadata)",
            "Official Jito tokenomics docs",
        ],
    )

    # Save
    path = store.save(jto)
    print(f"[OK] Updated JTO benchmark: {path}")

    # Verify
    loaded = store.load("JTO")
    print(f"\nVerification:")
    print(f"  Allocations: {len(loaded.allocations)} buckets")
    print(f"  Investors: {len(loaded.investors)} investors")
    print(f"  TGE Circulating: {loaded.tge_circulating_tokens:,} tokens")

    # Show allocations summary
    print(f"\nAllocations:")
    for a in loaded.allocations:
        print(f"  {a.bucket}: {a.percentage}% ({a.tokens:,} tokens) - TGE unlock: {a.tge_unlock_pct}%")


if __name__ == "__main__":
    main()
