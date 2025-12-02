#!/usr/bin/env python3
"""
Token Benchmark Report Generator

Generates beautiful, comprehensive reports for token benchmarks.
Includes tables, charts, and detailed analysis.
"""

import sys
from pathlib import Path
from typing import Optional

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.storage.json_store import BenchmarkStore, TokenBenchmark


def generate_terminal_report(symbol: str, store: Optional[BenchmarkStore] = None) -> None:
    """Generate a rich terminal report for a token."""
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        from rich.columns import Columns
        from rich.text import Text
        from rich import box
    except ImportError:
        print("[ERROR] rich not installed. Run: pip install rich")
        return

    if store is None:
        store = BenchmarkStore()

    benchmark = store.load(symbol)
    if not benchmark:
        print(f"[ERROR] {symbol} not found in database")
        return

    console = Console()

    # Header
    console.print()
    console.print(Panel(
        f"[bold white]{benchmark.name}[/bold white] ([cyan]{benchmark.symbol}[/cyan])",
        title="TOKEN BENCHMARK REPORT",
        subtitle=f"Generated from {benchmark.benchmark_method}",
        border_style="blue",
        padding=(1, 2),
    ))

    # === OVERVIEW SECTION ===
    console.print("\n[bold cyan]=== OVERVIEW ===[/bold cyan]\n")

    overview_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
    overview_table.add_column("Field", style="dim")
    overview_table.add_column("Value", style="white")

    overview_table.add_row("Blockchain", f"[yellow]{benchmark.blockchain}[/yellow]")
    overview_table.add_row("Categories", ", ".join(benchmark.categories))
    overview_table.add_row("Listing Date (TGE)", f"[green]{benchmark.listing_date}[/green]")
    overview_table.add_row("CoinGecko ID", benchmark.coingecko_id)

    console.print(overview_table)

    # === BENCHMARK PRICE SECTION ===
    console.print("\n[bold cyan]=== BENCHMARK PRICE DISCOVERY ===[/bold cyan]\n")

    confidence_color = {
        "HIGH": "green",
        "MEDIUM": "yellow",
        "LOW": "red",
        "UNKNOWN": "dim"
    }.get(benchmark.benchmark_confidence, "white")

    price_panel = Panel(
        f"[bold white on blue] ${benchmark.benchmark_price:.4f} [/bold white on blue]\n\n"
        f"Method: [cyan]{benchmark.benchmark_method.replace('_', ' ').title()}[/cyan]\n"
        f"Confidence: [{confidence_color}]{benchmark.benchmark_confidence}[/{confidence_color}]",
        title="BENCHMARK PRICE",
        border_style="green",
        padding=(1, 4),
    )
    console.print(price_panel)

    # Price Sources Table
    if benchmark.cex_data or benchmark.dex_stabilization:
        console.print("\n[bold]Price Sources Analysis:[/bold]\n")

        price_table = Table(title="CEX vs DEX Price Comparison", box=box.ROUNDED)
        price_table.add_column("Source", style="cyan")
        price_table.add_column("Type", style="dim")
        price_table.add_column("Time", style="dim")
        price_table.add_column("Price", justify="right", style="green")
        price_table.add_column("H/L Ratio", justify="right")
        price_table.add_column("Flag", style="yellow")

        # CEX data
        for cex in benchmark.cex_data:
            flag_style = "red" if "SUSPECT" in cex.flag else "yellow" if cex.is_tge_candle else "green"
            hl_style = "red" if cex.hl_ratio > 10 else "yellow" if cex.hl_ratio > 5 else "white"

            price_table.add_row(
                cex.exchange.upper(),
                "CEX",
                cex.first_candle_time.replace(" UTC", ""),
                f"${cex.open:.4f}",
                f"[{hl_style}]{cex.hl_ratio:.1f}x[/{hl_style}]",
                f"[{flag_style}]{cex.flag}[/{flag_style}]"
            )

            # Add VWAP if available
            if cex.vwap_1h:
                price_table.add_row(
                    f"  +- {cex.exchange.upper()} VWAP",
                    "1h avg",
                    "",
                    f"${cex.vwap_1h:.4f}",
                    "",
                    "[dim]Volume weighted[/dim]"
                )

        # DEX data
        if benchmark.dex_stabilization:
            dex = benchmark.dex_stabilization
            price_table.add_row("", "", "", "", "", "")  # Separator

            for dex_name, dex_price in dex.dex_prices.items():
                price_table.add_row(
                    dex_name.replace("_", " ").title(),
                    "DEX",
                    dex.stabilization_hour,
                    f"${dex_price:.4f}",
                    "",
                    f"[green]OK Stabilized[/green]"
                )

            # Summary row
            price_table.add_row(
                "[bold]DEX CONSENSUS[/bold]",
                "",
                "",
                f"[bold green]${dex.reference_price:.4f}[/bold green]",
                "",
                f"[green]Spread: {dex.spread_pct:.2f}%[/green]"
            )

        console.print(price_table)

    # === VALUATION SECTION ===
    console.print("\n[bold cyan]=== VALUATION AT TGE ===[/bold cyan]\n")

    val_table = Table(show_header=True, box=box.ROUNDED)
    val_table.add_column("Metric", style="cyan")
    val_table.add_column("Value", justify="right", style="white")
    val_table.add_column("Calculation", style="dim")

    val_table.add_row(
        "Fully Diluted Valuation (FDV)",
        f"[bold green]${benchmark.fdv_usd:,.0f}[/bold green]",
        f"{benchmark.total_supply:,} × ${benchmark.benchmark_price:.4f}"
    )
    val_table.add_row(
        "Market Cap (TGE)",
        f"${benchmark.mcap_usd:,.0f}",
        f"{benchmark.tge_circulating_pct}% × FDV"
    )

    if benchmark.total_raised:
        val_table.add_row(
            "FDV / Total Raised",
            f"[yellow]{benchmark.fdv_to_raised_ratio:.1f}x[/yellow]",
            f"${benchmark.fdv_usd:,.0f} / ${benchmark.total_raised:,}"
        )

    console.print(val_table)

    # === SUPPLY SECTION ===
    console.print("\n[bold cyan]=== TOKEN SUPPLY ===[/bold cyan]\n")

    supply_table = Table(show_header=True, box=box.ROUNDED)
    supply_table.add_column("Metric", style="cyan")
    supply_table.add_column("Tokens", justify="right")
    supply_table.add_column("Percentage", justify="right")

    supply_table.add_row(
        "Total Supply",
        f"{benchmark.total_supply:,}",
        "100%"
    )
    if benchmark.max_supply:
        supply_table.add_row(
            "Max Supply",
            f"{benchmark.max_supply:,}",
            f"{benchmark.max_supply/benchmark.total_supply*100:.1f}%"
        )
    supply_table.add_row(
        "Circulating at TGE",
        f"[green]{benchmark.tge_circulating_tokens:,}[/green]",
        f"[green]{benchmark.tge_circulating_pct}%[/green]"
    )
    if benchmark.current_circulating_tokens:
        current_pct = benchmark.current_circulating_tokens / benchmark.total_supply * 100
        supply_table.add_row(
            "Current Circulating",
            f"{benchmark.current_circulating_tokens:,}",
            f"{current_pct:.1f}%"
        )

    console.print(supply_table)

    # === ALLOCATIONS SECTION ===
    if benchmark.allocations:
        console.print("\n[bold cyan]=== TOKEN ALLOCATIONS ===[/bold cyan]\n")

        # Text-based bar chart
        console.print("[bold]Distribution Chart:[/bold]\n")

        max_bar_width = 40
        colors = ["blue", "green", "yellow", "magenta", "cyan", "red", "white"]

        for i, alloc in enumerate(benchmark.allocations):
            bar_width = int(alloc.percentage / 100 * max_bar_width)
            color = colors[i % len(colors)]
            bar = "#" * bar_width + "-" * (max_bar_width - bar_width)

            tge_info = f" (TGE: {alloc.tge_unlock_pct}%)" if alloc.tge_unlock_pct > 0 else ""

            console.print(
                f"  [{color}]{bar}[/{color}] "
                f"[bold]{alloc.percentage:5.1f}%[/bold] "
                f"{alloc.bucket}{tge_info}"
            )

        console.print()

        # Detailed allocations table
        alloc_table = Table(title="Allocation Details", box=box.ROUNDED)
        alloc_table.add_column("Bucket", style="cyan")
        alloc_table.add_column("Percentage", justify="right")
        alloc_table.add_column("Tokens", justify="right")
        alloc_table.add_column("TGE Unlock", justify="right")
        alloc_table.add_column("Vesting", style="dim")

        for alloc in benchmark.allocations:
            tge_style = "green" if alloc.tge_unlock_pct == 100 else "yellow" if alloc.tge_unlock_pct > 0 else "red"
            alloc_table.add_row(
                alloc.bucket,
                f"{alloc.percentage}%",
                f"{alloc.tokens:,}",
                f"[{tge_style}]{alloc.tge_unlock_pct}%[/{tge_style}]",
                alloc.vesting
            )

        console.print(alloc_table)

    # === FUNDRAISING SECTION ===
    if benchmark.fundraising_rounds:
        console.print("\n[bold cyan]=== FUNDRAISING HISTORY ===[/bold cyan]\n")

        fund_table = Table(title="Funding Rounds", box=box.ROUNDED)
        fund_table.add_column("Round", style="cyan")
        fund_table.add_column("Date", style="dim")
        fund_table.add_column("Amount", justify="right", style="green")
        fund_table.add_column("Valuation", justify="right")
        fund_table.add_column("Token Price", justify="right")
        fund_table.add_column("Lead Investors")

        for round in benchmark.fundraising_rounds:
            val_str = f"${round.valuation:,}" if round.valuation else "-"
            price_str = f"${round.token_price:.4f}" if round.token_price else "-"
            leads = ", ".join(round.lead_investors) if round.lead_investors else "-"

            fund_table.add_row(
                round.name,
                round.date,
                f"${round.amount:,}",
                val_str,
                price_str,
                leads
            )

        # Total row
        fund_table.add_row(
            "[bold]TOTAL[/bold]",
            "",
            f"[bold]${benchmark.total_raised:,}[/bold]",
            "",
            "",
            ""
        )

        console.print(fund_table)

    # === INVESTORS SECTION ===
    if benchmark.investors:
        console.print("\n[bold cyan]=== INVESTORS ===[/bold cyan]\n")

        investor_text = " * ".join(benchmark.investors)
        console.print(Panel(investor_text, border_style="dim"))

    # === METHODOLOGY SECTION ===
    if benchmark.methodology_notes:
        console.print("\n[bold cyan]=== METHODOLOGY NOTES ===[/bold cyan]\n")

        for note in benchmark.methodology_notes:
            console.print(f"  [dim]*[/dim] {note}")

    # === FOOTER ===
    console.print("\n")
    console.print(Panel(
        f"[dim]Sources: {', '.join(benchmark.sources)}[/dim]\n"
        f"[dim]Last Updated: {benchmark.last_updated}[/dim]",
        border_style="dim",
    ))
    console.print()


def generate_chart(symbol: str, store: Optional[BenchmarkStore] = None, output_path: Optional[str] = None) -> str:
    """Generate allocation pie chart as image."""
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError:
        print("[ERROR] matplotlib not installed. Run: pip install matplotlib")
        return ""

    if store is None:
        store = BenchmarkStore()

    benchmark = store.load(symbol)
    if not benchmark or not benchmark.allocations:
        print(f"[ERROR] {symbol} not found or has no allocations")
        return ""

    # Setup figure with subplots
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle(f'{benchmark.name} ({benchmark.symbol}) - Token Allocation', fontsize=16, fontweight='bold')

    # Color palette
    colors = ['#3498db', '#2ecc71', '#f1c40f', '#9b59b6', '#e74c3c', '#1abc9c', '#34495e', '#e67e22']

    # === PIE CHART ===
    ax1 = axes[0]

    labels = [a.bucket for a in benchmark.allocations]
    sizes = [a.percentage for a in benchmark.allocations]

    wedges, texts, autotexts = ax1.pie(
        sizes,
        labels=None,
        autopct='%1.1f%%',
        colors=colors[:len(sizes)],
        startangle=90,
        explode=[0.02] * len(sizes),
        shadow=True,
        textprops={'fontsize': 10}
    )

    ax1.set_title('Token Distribution', fontsize=12, pad=10)

    # Legend
    ax1.legend(
        wedges, labels,
        title="Allocations",
        loc="center left",
        bbox_to_anchor=(0.9, 0.5),
        fontsize=9
    )

    # === BAR CHART (TGE Unlock) ===
    ax2 = axes[1]

    buckets = [a.bucket for a in benchmark.allocations]
    tge_unlocks = [a.tge_unlock_pct for a in benchmark.allocations]
    locked = [100 - u for u in tge_unlocks]

    x = range(len(buckets))
    width = 0.6

    bars1 = ax2.bar(x, tge_unlocks, width, label='Unlocked at TGE', color='#2ecc71')
    bars2 = ax2.bar(x, locked, width, bottom=tge_unlocks, label='Locked/Vesting', color='#e74c3c', alpha=0.7)

    ax2.set_ylabel('Percentage')
    ax2.set_title('TGE Unlock vs Locked', fontsize=12, pad=10)
    ax2.set_xticks(x)
    ax2.set_xticklabels(buckets, rotation=45, ha='right', fontsize=9)
    ax2.legend(loc='upper right')
    ax2.set_ylim(0, 110)

    # Add percentage labels on bars
    for bar, val in zip(bars1, tge_unlocks):
        if val > 5:
            ax2.text(bar.get_x() + bar.get_width()/2, val/2, f'{val:.0f}%',
                    ha='center', va='center', color='white', fontweight='bold', fontsize=9)

    plt.tight_layout()

    # Save
    if output_path is None:
        output_path = str(Path(__file__).parent.parent / "data" / "reports" / f"{symbol.lower()}_allocation.png")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()

    return output_path


def generate_price_chart(symbol: str, store: Optional[BenchmarkStore] = None, output_path: Optional[str] = None) -> str:
    """Generate price comparison chart."""
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("[ERROR] matplotlib not installed. Run: pip install matplotlib")
        return ""

    if store is None:
        store = BenchmarkStore()

    benchmark = store.load(symbol)
    if not benchmark:
        print(f"[ERROR] {symbol} not found")
        return ""

    fig, ax = plt.subplots(figsize=(12, 6))
    fig.suptitle(f'{benchmark.name} ({benchmark.symbol}) - Price Discovery at TGE', fontsize=14, fontweight='bold')

    prices = []
    labels = []
    colors_list = []

    # CEX prices
    for cex in benchmark.cex_data:
        # Open price
        prices.append(cex.open)
        labels.append(f"{cex.exchange.upper()}\nOpen")
        colors_list.append('#e74c3c' if 'SUSPECT' in cex.flag else '#f39c12')

        # VWAP if available
        if cex.vwap_1h:
            prices.append(cex.vwap_1h)
            labels.append(f"{cex.exchange.upper()}\nVWAP 1h")
            colors_list.append('#3498db')

    # DEX prices
    if benchmark.dex_stabilization:
        for dex_name, dex_price in benchmark.dex_stabilization.dex_prices.items():
            prices.append(dex_price)
            short_name = dex_name.replace("_", " ").split()[0].title()
            labels.append(f"{short_name}\nDEX")
            colors_list.append('#2ecc71')

    # Benchmark price
    prices.append(benchmark.benchmark_price)
    labels.append("BENCHMARK\nPRICE")
    colors_list.append('#9b59b6')

    # Create bar chart
    x = np.arange(len(prices))
    bars = ax.bar(x, prices, color=colors_list, edgecolor='black', linewidth=0.5)

    # Add value labels
    for bar, price in zip(bars, prices):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                f'${price:.4f}', ha='center', va='bottom', fontsize=8, rotation=0)

    # Benchmark line
    ax.axhline(y=benchmark.benchmark_price, color='#9b59b6', linestyle='--', linewidth=2, label='Benchmark Price')

    ax.set_ylabel('Price (USD)')
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8)

    # Legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor='#f39c12', label='CEX Open'),
        Patch(facecolor='#3498db', label='CEX VWAP'),
        Patch(facecolor='#2ecc71', label='DEX Stabilized'),
        Patch(facecolor='#9b59b6', label='Benchmark'),
    ]
    ax.legend(handles=legend_elements, loc='upper right')

    plt.tight_layout()

    # Save
    if output_path is None:
        output_path = str(Path(__file__).parent.parent / "data" / "reports" / f"{symbol.lower()}_price.png")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()

    return output_path


def generate_full_report(symbol: str) -> None:
    """Generate complete report with terminal output and charts."""
    store = BenchmarkStore()

    print(f"\n[*] Generating full report for {symbol}...\n")

    # Terminal report
    generate_terminal_report(symbol, store)

    # Charts
    alloc_path = generate_chart(symbol, store)
    if alloc_path:
        print(f"[OK] Allocation chart saved: {alloc_path}")

    price_path = generate_price_chart(symbol, store)
    if price_path:
        print(f"[OK] Price chart saved: {price_path}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m src.report <SYMBOL>")
        print("Example: python -m src.report JTO")
        sys.exit(1)

    symbol = sys.argv[1].upper()
    generate_full_report(symbol)
