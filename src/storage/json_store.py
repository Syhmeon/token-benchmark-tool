#!/usr/bin/env python3
"""
JSON-based storage for token benchmarks.

Simple, file-based storage that persists benchmark data as JSON files.
Each token gets its own file in data/benchmarks/{symbol}.json
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any


@dataclass
class PriceSource:
    """A price data point from a specific source."""
    source: str  # "bybit", "binance", "dex_orca", etc.
    price: float
    timestamp: str
    reliability: str  # "HIGH", "MEDIUM", "LOW"
    note: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None


@dataclass
class DEXStabilization:
    """DEX price stabilization data."""
    stabilization_hour: str
    reference_price: float
    spread_pct: float
    confidence: str
    dex_prices: Dict[str, float] = field(default_factory=dict)
    total_swaps: int = 0
    # First DEX data (for tokens where DEX trading starts before CEX)
    first_dex: Optional[str] = None  # e.g., "uniswap_v3"
    first_dex_time: Optional[str] = None  # e.g., "2024-10-01 03:35:00 UTC"
    first_candles_1m: List[Dict[str, Any]] = field(default_factory=list)  # First 10 1-minute candles


@dataclass
class CEXData:
    """CEX price data for first candles."""
    exchange: str
    first_candle_time: str
    open: float
    high: float
    low: float
    close: float
    hl_ratio: float
    is_tge_candle: bool
    flag: str
    vwap_1h: Optional[float] = None
    median_close_1h: Optional[float] = None
    # First 10 1-minute candles for price discovery analysis
    first_candles_1m: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class FundraisingRound:
    """A fundraising round."""
    name: str
    date: str
    amount: int
    valuation: Optional[int] = None
    lead_investors: List[str] = field(default_factory=list)
    token_price: Optional[float] = None
    source: str = ""  # e.g., "CryptoRank", "Messari"


@dataclass
class TokenAllocation:
    """Token allocation bucket."""
    bucket: str  # "Airdrop", "Team", "Investors", "Community", "Ecosystem", etc.
    percentage: float
    tokens: int
    vesting: str  # e.g., "3 years, 1 year cliff" or "TGE 100%"
    tge_unlock_pct: float = 0.0  # Percentage unlocked at TGE
    cliff_months: int = 0  # Months before vesting starts
    vesting_months: int = 0  # Total vesting duration in months


@dataclass
class HolderData:
    """Token holder distribution data."""
    total_holders: int = 0
    top_10_pct: float = 0.0  # % of supply held by top 10
    top_50_pct: float = 0.0  # % of supply held by top 50
    top_100_pct: float = 0.0  # % of supply held by top 100
    top_holders: List[Dict[str, Any]] = field(default_factory=list)  # [{address, balance, pct}]
    source: str = ""  # "flipside", "cmc", etc.
    snapshot_date: str = ""
    notes: Optional[str] = None  # Additional notes about data discrepancies, methodology, etc.


@dataclass
class TokenBenchmark:
    """Complete benchmark data for a token."""
    # Basic info
    symbol: str
    name: str
    coingecko_id: str
    blockchain: str
    categories: List[str] = field(default_factory=list)
    listing_date: str = ""
    description: str = ""  # One-sentence description in English

    # Supply
    total_supply: int = 0
    max_supply: Optional[int] = None
    tge_circulating_pct: float = 0.0
    tge_circulating_tokens: int = 0
    current_circulating_tokens: int = 0

    # Benchmark valuation
    benchmark_price: float = 0.0
    benchmark_method: str = ""  # "dex_stabilization", "cex_vwap", "manual"
    benchmark_confidence: str = "UNKNOWN"
    fdv_usd: float = 0.0
    mcap_usd: float = 0.0

    # Price sources
    cex_data: List[CEXData] = field(default_factory=list)
    dex_stabilization: Optional[DEXStabilization] = None

    # Fundraising
    total_raised: int = 0
    fundraising_rounds: List[FundraisingRound] = field(default_factory=list)
    fdv_to_raised_ratio: float = 0.0
    investors: List[str] = field(default_factory=list)

    # Token allocations
    allocations: List[TokenAllocation] = field(default_factory=list)

    # Holder distribution
    holders: Optional[HolderData] = None

    # Metadata
    methodology_notes: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    last_updated: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data["last_updated"] = datetime.now(timezone.utc).isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TokenBenchmark":
        """Create from dictionary."""
        # Handle nested dataclasses
        if "cex_data" in data and data["cex_data"]:
            data["cex_data"] = [
                CEXData(**c) if isinstance(c, dict) else c
                for c in data["cex_data"]
            ]

        if "dex_stabilization" in data and data["dex_stabilization"]:
            if isinstance(data["dex_stabilization"], dict):
                data["dex_stabilization"] = DEXStabilization(**data["dex_stabilization"])

        if "fundraising_rounds" in data and data["fundraising_rounds"]:
            data["fundraising_rounds"] = [
                FundraisingRound(**r) if isinstance(r, dict) else r
                for r in data["fundraising_rounds"]
            ]

        if "allocations" in data and data["allocations"]:
            data["allocations"] = [
                TokenAllocation(**a) if isinstance(a, dict) else a
                for a in data["allocations"]
            ]

        if "holders" in data and data["holders"]:
            if isinstance(data["holders"], dict):
                data["holders"] = HolderData(**data["holders"])

        return cls(**data)


class BenchmarkStore:
    """
    JSON-based storage for token benchmarks.

    Usage:
        store = BenchmarkStore()

        # Save benchmark
        benchmark = TokenBenchmark(symbol="JTO", ...)
        store.save(benchmark)

        # Load benchmark
        jto = store.load("JTO")

        # List all
        all_tokens = store.list_all()
    """

    def __init__(self, data_dir: Optional[Path] = None):
        """Initialize store with data directory."""
        if data_dir is None:
            # Default to token_listing_tool/data/benchmarks
            data_dir = Path(__file__).parent.parent.parent / "data" / "benchmarks"

        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, symbol: str) -> Path:
        """Get file path for a token symbol."""
        return self.data_dir / f"{symbol.lower()}.json"

    def save(self, benchmark: TokenBenchmark) -> Path:
        """
        Save a benchmark to JSON file.

        Returns the path to the saved file.
        """
        path = self._get_path(benchmark.symbol)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(benchmark.to_dict(), f, indent=2, ensure_ascii=False)

        return path

    def load(self, symbol: str) -> Optional[TokenBenchmark]:
        """
        Load a benchmark from JSON file.

        Returns None if file doesn't exist.
        """
        path = self._get_path(symbol)

        if not path.exists():
            return None

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return TokenBenchmark.from_dict(data)

    def exists(self, symbol: str) -> bool:
        """Check if benchmark exists for symbol."""
        return self._get_path(symbol).exists()

    def delete(self, symbol: str) -> bool:
        """Delete benchmark file. Returns True if deleted."""
        path = self._get_path(symbol)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_all(self) -> List[str]:
        """List all stored token symbols."""
        return [
            p.stem.upper()
            for p in self.data_dir.glob("*.json")
        ]

    def load_all(self) -> List[TokenBenchmark]:
        """Load all benchmarks."""
        return [
            self.load(symbol)
            for symbol in self.list_all()
            if self.load(symbol) is not None
        ]

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all benchmarks."""
        benchmarks = self.load_all()

        if not benchmarks:
            return {"count": 0, "tokens": []}

        summary = {
            "count": len(benchmarks),
            "tokens": [],
            "total_fdv": sum(b.fdv_usd for b in benchmarks),
            "avg_fdv_to_raised": sum(b.fdv_to_raised_ratio for b in benchmarks if b.fdv_to_raised_ratio) / len([b for b in benchmarks if b.fdv_to_raised_ratio]) if any(b.fdv_to_raised_ratio for b in benchmarks) else 0,
        }

        for b in benchmarks:
            summary["tokens"].append({
                "symbol": b.symbol,
                "blockchain": b.blockchain,
                "fdv_usd": b.fdv_usd,
                "benchmark_price": b.benchmark_price,
                "confidence": b.benchmark_confidence,
                "fdv_to_raised": b.fdv_to_raised_ratio,
            })

        return summary


# Convenience function to create JTO benchmark from existing data
def create_jto_benchmark() -> TokenBenchmark:
    """Create JTO benchmark from analyzed data."""
    return TokenBenchmark(
        symbol="JTO",
        name="Jito",
        coingecko_id="jito-governance-token",
        blockchain="Solana",
        categories=["Liquid Staking", "MEV Infrastructure", "DeFi"],
        listing_date="2023-12-07",
        total_supply=1_000_000_000,
        tge_circulating_pct=11.5,

        benchmark_price=2.0352,
        benchmark_method="dex_stabilization",
        benchmark_confidence="HIGH",
        fdv_usd=2_035_200_000,
        mcap_usd=234_048_000,

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

        total_raised=12_100_000,
        fundraising_rounds=[
            FundraisingRound(name="Seed", date="2021-12", amount=2_100_000),
            FundraisingRound(name="Series A", date="2022-08", amount=10_000_000),
        ],
        fdv_to_raised_ratio=168.2,

        methodology_notes=[
            "CEX first candles show H/L ratio > 30x - flagged as TGE candles",
            "Bybit shows impossible wicks ($32) vs ATH ($5.91) - marked SUSPECT",
            "DEX stabilization at +2h when 5 protocols converge within 0.41% spread",
            "Benchmark price = volume-weighted average of DEX prices at stabilization",
        ],
        sources=[
            "CCXT (Bybit, Binance)",
            "Flipside (Solana DEX)",
            "CoinGecko (metadata)",
        ],
    )


if __name__ == "__main__":
    # Test the store
    store = BenchmarkStore()

    # Create and save JTO benchmark
    jto = create_jto_benchmark()
    path = store.save(jto)
    print(f"Saved JTO benchmark to: {path}")

    # Load and verify
    loaded = store.load("JTO")
    print(f"\nLoaded: {loaded.symbol}")
    print(f"  FDV: ${loaded.fdv_usd:,.0f}")
    print(f"  Benchmark Price: ${loaded.benchmark_price}")
    print(f"  Confidence: {loaded.benchmark_confidence}")

    # Show summary
    print("\n" + "=" * 50)
    summary = store.get_summary()
    print(f"Total benchmarks: {summary['count']}")
    for t in summary["tokens"]:
        print(f"  {t['symbol']}: ${t['fdv_usd']:,.0f} FDV ({t['confidence']})")
