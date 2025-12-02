#!/usr/bin/env python3
"""
Token Benchmark Analyzer

Generic analyzer for any token. Workflow:
1. Check if token already exists in database
2. If not, fetch metadata from CoinGecko
3. Fetch CEX data via CCXT
4. Accept DEX data input (from FlipsideAI - manual)
5. Calculate benchmark FDV and save

Usage:
    from src.analyzer import TokenAnalyzer

    analyzer = TokenAnalyzer()

    # Check if token exists
    if analyzer.exists("JTO"):
        benchmark = analyzer.get("JTO")
    else:
        # Analyze new token
        benchmark = analyzer.analyze(
            symbol="JTO",
            coingecko_id="jito-governance-token",
            listing_date="2023-12-07",
            dex_data={...}  # From FlipsideAI
        )
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pathlib import Path

from .storage.json_store import (
    BenchmarkStore,
    TokenBenchmark,
    CEXData,
    DEXStabilization,
    FundraisingRound,
)


class TokenAnalyzer:
    """
    Generic token benchmark analyzer.

    Works with any token - no hardcoded values.
    """

    def __init__(self, data_dir: Optional[Path] = None):
        """Initialize analyzer with storage."""
        self.store = BenchmarkStore(data_dir)

    def exists(self, symbol: str) -> bool:
        """Check if benchmark exists for token."""
        return self.store.exists(symbol)

    def get(self, symbol: str) -> Optional[TokenBenchmark]:
        """Get existing benchmark for token."""
        return self.store.load(symbol)

    def list_all(self) -> List[str]:
        """List all tokens in database."""
        return self.store.list_all()

    def analyze(
        self,
        # Required token info
        symbol: str,
        name: str,
        coingecko_id: str,
        blockchain: str,
        listing_date: str,
        total_supply: int,
        tge_circulating_pct: float,
        # Optional metadata
        categories: Optional[List[str]] = None,
        # DEX data (from FlipsideAI - manual input)
        dex_reference_price: Optional[float] = None,
        dex_stabilization_hour: Optional[str] = None,
        dex_spread_pct: Optional[float] = None,
        dex_prices: Optional[Dict[str, float]] = None,
        dex_total_swaps: Optional[int] = None,
        # Fundraising (optional)
        total_raised: Optional[int] = None,
        fundraising_rounds: Optional[List[Dict]] = None,
        # CEX data (auto-fetched or manual)
        cex_data: Optional[List[Dict]] = None,
        fetch_cex: bool = True,
        # Override if exists
        force: bool = False,
    ) -> TokenBenchmark:
        """
        Analyze a token and create benchmark.

        Args:
            symbol: Token symbol (e.g., "JTO")
            name: Token name (e.g., "Jito")
            coingecko_id: CoinGecko ID for the token
            blockchain: Blockchain name (e.g., "Solana", "Ethereum")
            listing_date: TGE date in YYYY-MM-DD format
            total_supply: Total token supply
            tge_circulating_pct: Percentage circulating at TGE
            categories: Token categories (e.g., ["DeFi", "Liquid Staking"])
            dex_reference_price: DEX stabilization price (from FlipsideAI)
            dex_stabilization_hour: Hour when DEX prices stabilized
            dex_spread_pct: Spread between DEX prices at stabilization
            dex_prices: Dict of DEX name -> price at stabilization
            dex_total_swaps: Total swaps in stabilization period
            total_raised: Total fundraising amount in USD
            fundraising_rounds: List of fundraising rounds
            cex_data: Manual CEX data (if not auto-fetching)
            fetch_cex: Whether to auto-fetch CEX data via CCXT
            force: Overwrite existing benchmark if exists

        Returns:
            TokenBenchmark object (also saved to database)
        """
        # Check if already exists
        if self.exists(symbol) and not force:
            print(f"[INFO] {symbol} already exists in database. Use force=True to overwrite.")
            return self.get(symbol)

        # Prepare CEX data
        cex_list = []
        if cex_data:
            for cex in cex_data:
                cex_list.append(CEXData(**cex))
        elif fetch_cex:
            cex_list = self._fetch_cex_data(symbol, listing_date)

        # Prepare DEX stabilization data
        dex_stab = None
        if dex_reference_price:
            dex_stab = DEXStabilization(
                stabilization_hour=dex_stabilization_hour or "",
                reference_price=dex_reference_price,
                spread_pct=dex_spread_pct or 0.0,
                confidence="HIGH" if (dex_spread_pct and dex_spread_pct < 1.0) else "MEDIUM",
                dex_prices=dex_prices or {},
                total_swaps=dex_total_swaps or 0,
            )

        # Calculate benchmark values
        benchmark_price = dex_reference_price or 0.0
        benchmark_method = "dex_stabilization" if dex_reference_price else "pending"
        benchmark_confidence = dex_stab.confidence if dex_stab else "UNKNOWN"

        fdv_usd = total_supply * benchmark_price if benchmark_price else 0.0
        mcap_usd = total_supply * (tge_circulating_pct / 100) * benchmark_price if benchmark_price else 0.0

        # Prepare fundraising
        rounds = []
        if fundraising_rounds:
            for r in fundraising_rounds:
                rounds.append(FundraisingRound(**r))

        fdv_to_raised = fdv_usd / total_raised if (fdv_usd and total_raised) else 0.0

        # Create benchmark
        benchmark = TokenBenchmark(
            symbol=symbol,
            name=name,
            coingecko_id=coingecko_id,
            blockchain=blockchain,
            categories=categories or [],
            listing_date=listing_date,
            total_supply=total_supply,
            tge_circulating_pct=tge_circulating_pct,
            benchmark_price=benchmark_price,
            benchmark_method=benchmark_method,
            benchmark_confidence=benchmark_confidence,
            fdv_usd=fdv_usd,
            mcap_usd=mcap_usd,
            cex_data=cex_list,
            dex_stabilization=dex_stab,
            total_raised=total_raised or 0,
            fundraising_rounds=rounds,
            fdv_to_raised_ratio=round(fdv_to_raised, 1),
            methodology_notes=self._generate_notes(cex_list, dex_stab),
            sources=self._list_sources(cex_list, dex_stab),
        )

        # Save to database
        path = self.store.save(benchmark)
        print(f"[OK] Saved {symbol} benchmark to {path}")

        return benchmark

    def _fetch_cex_data(self, symbol: str, listing_date: str) -> List[CEXData]:
        """
        Fetch CEX data via CCXT.

        This is a simplified version - real implementation would
        query multiple exchanges and find first candles.
        """
        try:
            import ccxt
            from datetime import datetime

            cex_list = []
            exchanges = ["binance", "bybit", "okx", "kucoin"]
            pair = f"{symbol}/USDT"

            # Parse listing date
            listing_dt = datetime.strptime(listing_date, "%Y-%m-%d")
            listing_dt = listing_dt.replace(hour=0, minute=0, second=0, tzinfo=timezone.utc)
            since_ms = int(listing_dt.timestamp() * 1000)

            for exchange_id in exchanges:
                try:
                    exchange = getattr(ccxt, exchange_id)({"enableRateLimit": True})
                    exchange.load_markets()

                    if pair not in exchange.markets:
                        continue

                    candles = exchange.fetch_ohlcv(pair, "1m", since=since_ms, limit=60)

                    if candles:
                        first = candles[0]
                        hl_ratio = first[2] / first[3] if first[3] > 0 else 999

                        # Calculate VWAP for first hour
                        vwap = self._calculate_vwap(candles)
                        median_close = self._calculate_median_close(candles)

                        cex_list.append(CEXData(
                            exchange=exchange_id,
                            first_candle_time=datetime.fromtimestamp(first[0]/1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                            open=first[1],
                            high=first[2],
                            low=first[3],
                            close=first[4],
                            hl_ratio=round(hl_ratio, 1),
                            is_tge_candle=hl_ratio > 5,
                            flag="TGE candle" if hl_ratio > 5 else "OK",
                            vwap_1h=vwap,
                            median_close_1h=median_close,
                        ))

                except Exception as e:
                    print(f"[WARN] {exchange_id}: {e}")
                    continue

            return cex_list

        except ImportError:
            print("[WARN] ccxt not installed, skipping CEX data fetch")
            return []

    def _calculate_vwap(self, candles: List) -> float:
        """Calculate Volume Weighted Average Price."""
        if not candles:
            return 0.0
        typical_prices = [(c[2] + c[3] + c[4]) / 3 for c in candles]
        volumes = [c[5] for c in candles]
        vwap_num = sum(tp * v for tp, v in zip(typical_prices, volumes))
        vwap_denom = sum(volumes)
        return round(vwap_num / vwap_denom, 4) if vwap_denom > 0 else 0.0

    def _calculate_median_close(self, candles: List) -> float:
        """Calculate median close price."""
        if not candles:
            return 0.0
        closes = sorted([c[4] for c in candles])
        n = len(closes)
        if n % 2 == 0:
            return round((closes[n//2 - 1] + closes[n//2]) / 2, 4)
        return round(closes[n//2], 4)

    def _generate_notes(self, cex_data: List[CEXData], dex_stab: Optional[DEXStabilization]) -> List[str]:
        """Generate methodology notes based on data."""
        notes = []

        # CEX notes
        tge_candles = [c for c in cex_data if c.is_tge_candle]
        if tge_candles:
            notes.append(f"CEX first candles show H/L ratio > 5x on {len(tge_candles)} exchanges - flagged as TGE candles")

        # DEX notes
        if dex_stab:
            notes.append(f"DEX stabilization when {len(dex_stab.dex_prices)} protocols converge within {dex_stab.spread_pct:.2f}% spread")
            notes.append("Benchmark price = volume-weighted average of DEX prices at stabilization")

        return notes

    def _list_sources(self, cex_data: List[CEXData], dex_stab: Optional[DEXStabilization]) -> List[str]:
        """List data sources used."""
        sources = []

        if cex_data:
            exchanges = [c.exchange.capitalize() for c in cex_data]
            sources.append(f"CCXT ({', '.join(exchanges)})")

        if dex_stab and dex_stab.dex_prices:
            sources.append(f"Flipside ({len(dex_stab.dex_prices)} DEX)")

        return sources

    def display(self, symbol: str) -> None:
        """Display benchmark for a token."""
        benchmark = self.get(symbol)

        if not benchmark:
            print(f"[ERROR] {symbol} not found in database")
            return

        print("=" * 60)
        print(f"TOKEN BENCHMARK: {benchmark.name} ({benchmark.symbol})")
        print("=" * 60)
        print(f"  Blockchain: {benchmark.blockchain}")
        print(f"  Categories: {', '.join(benchmark.categories)}")
        print(f"  Listing Date: {benchmark.listing_date}")
        print()
        print("VALUATION:")
        print(f"  Benchmark Price: ${benchmark.benchmark_price:.4f}")
        print(f"  Method: {benchmark.benchmark_method}")
        print(f"  Confidence: {benchmark.benchmark_confidence}")
        print(f"  FDV: ${benchmark.fdv_usd:,.0f}")
        print(f"  MCap (TGE): ${benchmark.mcap_usd:,.0f}")
        print()
        if benchmark.total_raised:
            print("FUNDRAISING:")
            print(f"  Total Raised: ${benchmark.total_raised:,}")
            print(f"  FDV/Raised: {benchmark.fdv_to_raised_ratio}x")
        print()
        print("SOURCES:", ", ".join(benchmark.sources))
        print("=" * 60)


# Convenience function
def quick_analyze(symbol: str, **kwargs) -> TokenBenchmark:
    """Quick analysis helper."""
    analyzer = TokenAnalyzer()
    return analyzer.analyze(symbol=symbol, **kwargs)
