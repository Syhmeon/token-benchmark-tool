#!/usr/bin/env python3
"""Update JTO benchmark with new fields: description, first_candles_1m, sources."""

import sys
from pathlib import Path

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

    # First 10 1-minute candles from Bybit (JTO/USDT) - 2023-12-07 starting 16:00 UTC
    bybit_first_candles = [
        {"minute": 1, "time": "16:00:00", "open": 0.03, "high": 3.00, "low": 0.03, "close": 3.00},
        {"minute": 2, "time": "16:01:00", "open": 3.00, "high": 3.10, "low": 3.00, "close": 3.00},
        {"minute": 3, "time": "16:02:00", "open": 3.00, "high": 3.00, "low": 3.00, "close": 3.00},
        {"minute": 4, "time": "16:03:00", "open": 3.00, "high": 3.00, "low": 3.00, "close": 3.00},
        {"minute": 5, "time": "16:04:00", "open": 3.00, "high": 3.00, "low": 3.00, "close": 3.00},
        {"minute": 6, "time": "16:05:00", "open": 3.00, "high": 10.61, "low": 3.00, "close": 10.00},
        {"minute": 7, "time": "16:06:00", "open": 10.00, "high": 32.67, "low": 10.00, "close": 28.00},
        {"minute": 8, "time": "16:07:00", "open": 28.00, "high": 28.65, "low": 9.50, "close": 9.50},
        {"minute": 9, "time": "16:08:00", "open": 9.50, "high": 11.24, "low": 7.00, "close": 10.68},
        {"minute": 10, "time": "16:09:00", "open": 10.68, "high": 15.00, "low": 10.00, "close": 14.42},
    ]

    # Create complete JTO benchmark with new fields
    jto = TokenBenchmark(
        symbol="JTO",
        name="Jito",
        coingecko_id="jito-governance-token",
        blockchain="Solana",
        categories=["Liquid Staking", "MEV Infrastructure", "DeFi"],
        listing_date="2023-12-07",
        description="Jito is a liquid staking protocol on Solana offering MEV-powered yields through JitoSOL.",

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

        # CEX Data with first 10 candles
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
                first_candles_1m=bybit_first_candles,
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
                first_candles_1m=[],  # Binance listed 30min later
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

        # Fundraising with sources
        total_raised=12_100_000,
        fundraising_rounds=[
            FundraisingRound(
                name="Seed",
                date="2021-12",
                amount=2_100_000,
                valuation=None,
                lead_investors=["Multicoin Capital"],
                token_price=None,
                source="CryptoRank",
            ),
            FundraisingRound(
                name="Series A",
                date="2022-08",
                amount=10_000_000,
                valuation=None,
                lead_investors=["Multicoin Capital", "Framework Ventures"],
                token_price=None,
                source="CryptoRank",
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
            "CryptoRank (fundraising)",
        ],
    )

    # Save
    path = store.save(jto)
    print(f"[OK] Updated JTO benchmark: {path}")

    # Verify
    loaded = store.load("JTO")
    print(f"\nVerification:")
    print(f"  Description: {loaded.description}")
    print(f"  First candles (Bybit): {len(loaded.cex_data[0].first_candles_1m)} candles")
    print(f"  Fundraising sources: {[r.source for r in loaded.fundraising_rounds]}")


if __name__ == "__main__":
    main()
