"""Pytest configuration and fixtures for token listing tool tests."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from src.core.models import (
    ExchangeCandle,
    ExchangeListing,
    RawAllocation,
    SourceReference,
    TokenInfo,
    VestingTerms,
)
from src.core.types import DataSource, VestingScheduleType


@pytest.fixture
def fixtures_dir() -> Path:
    """Return path to fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_token_info() -> TokenInfo:
    """Sample TokenInfo for Arbitrum."""
    return TokenInfo(
        coingecko_id="arbitrum",
        symbol="ARB",
        name="Arbitrum",
        contract_addresses={
            "arbitrum-one": "0x912CE59144191C1204E64559FE8253a0e49E6548",
            "ethereum": "0xB50721BCf8d664c30412Cfbc6cf7a15145234ad1",
        },
        categories=["Layer 2 (L2)", "Ethereum Ecosystem", "Arbitrum Ecosystem"],
        genesis_date=datetime(2023, 3, 23, tzinfo=timezone.utc),
        source=SourceReference(
            source=DataSource.COINGECKO,
            url="https://www.coingecko.com/en/coins/arbitrum",
        ),
    )


@pytest.fixture
def sample_candle() -> ExchangeCandle:
    """Sample exchange candle."""
    return ExchangeCandle(
        timestamp=datetime(2023, 3, 23, 10, 0, 0, tzinfo=timezone.utc),
        open=1.25,
        high=1.45,
        low=1.10,
        close=1.35,
        volume=1000000.0,
        volume_usd=1250000.0,
    )


@pytest.fixture
def sample_exchange_listing(sample_candle: ExchangeCandle) -> ExchangeListing:
    """Sample exchange listing."""
    return ExchangeListing(
        exchange="binance",
        trading_pair="ARB/USDT",
        base_currency="ARB",
        quote_currency="USDT",
        first_candle=sample_candle,
        timeframe="1h",
        source=SourceReference(
            source=DataSource.CCXT,
            endpoint="binance/ohlcv/ARB/USDT/1h",
        ),
    )


@pytest.fixture
def sample_raw_allocations() -> list[RawAllocation]:
    """Sample raw allocation data."""
    return [
        RawAllocation(
            source=DataSource.CRYPTORANK,
            label="Team",
            percentage=15.0,
            vesting=VestingTerms(
                tge_unlock_pct=0.0,
                cliff_months=12,
                vesting_months=36,
                schedule_type=VestingScheduleType.LINEAR,
            ),
        ),
        RawAllocation(
            source=DataSource.CRYPTORANK,
            label="Investors",
            percentage=17.53,
            vesting=VestingTerms(
                tge_unlock_pct=10.0,
                cliff_months=12,
                vesting_months=36,
                schedule_type=VestingScheduleType.LINEAR,
            ),
        ),
        RawAllocation(
            source=DataSource.CRYPTORANK,
            label="Airdrop",
            percentage=11.62,
            vesting=VestingTerms(
                tge_unlock_pct=100.0,
            ),
        ),
        RawAllocation(
            source=DataSource.CRYPTORANK,
            label="Treasury",
            percentage=42.78,
        ),
        RawAllocation(
            source=DataSource.CRYPTORANK,
            label="Foundation",
            percentage=7.5,
        ),
    ]


@pytest.fixture
def mock_coingecko_response() -> dict[str, Any]:
    """Mock CoinGecko API response for ARB."""
    return {
        "id": "arbitrum",
        "symbol": "arb",
        "name": "Arbitrum",
        "platforms": {
            "arbitrum-one": "0x912CE59144191C1204E64559FE8253a0e49E6548",
            "ethereum": "0xB50721BCf8d664c30412Cfbc6cf7a15145234ad1",
        },
        "categories": ["Layer 2 (L2)", "Ethereum Ecosystem"],
        "genesis_date": "2023-03-23",
        "market_data": {
            "total_supply": 10000000000,
            "max_supply": 10000000000,
            "circulating_supply": 3475000000,
        },
    }


@pytest.fixture
def mock_cryptorank_response() -> dict[str, Any]:
    """Mock CryptoRank API response."""
    return {
        "data": {
            "key": "arbitrum",
            "name": "Arbitrum",
            "symbol": "ARB",
            "fundingRounds": [
                {
                    "roundType": "Series B",
                    "raise": 120000000,
                    "date": "2022-02-01T00:00:00Z",
                    "investors": [
                        {"name": "Lightspeed Venture Partners", "isLead": True},
                        {"name": "Polychain Capital", "isLead": False},
                    ],
                },
                {
                    "roundType": "Series A",
                    "raise": 20000000,
                    "date": "2021-04-01T00:00:00Z",
                    "investors": [
                        {"name": "Lightspeed Venture Partners", "isLead": True},
                    ],
                },
            ],
            "tokenDistribution": [
                {"name": "Team", "percentage": 15.0},
                {"name": "Investors", "percentage": 17.53},
                {"name": "Airdrop", "percentage": 11.62},
                {"name": "Treasury", "percentage": 42.78},
                {"name": "Foundation", "percentage": 7.5},
            ],
        }
    }
