"""CLI entry point for the Token Listing FDV and Allocation Benchmark Tool.

Usage:
    token-listing analyze ARB
    token-listing analyze arbitrum --output json --save results/arb.json
    token-listing analyze ARB --circulating-supply 1275000000
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler

from ..orchestrator import TokenListingOrchestrator
from ..output.formatters import JSONFormatter, CSVFormatter, TableFormatter
from ..output.audit_trail import AuditTrailFormatter
from ..core.types import PriceSelectionMethod

# Initialize app
app = typer.Typer(
    name="token-listing",
    help="Token Listing FDV and Allocation Benchmark Tool",
    add_completion=False,
)

console = Console()


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, show_time=False, show_path=False)],
    )


@app.command()
def analyze(
    token: str = typer.Argument(..., help="Token symbol or CoinGecko ID (e.g., ARB, arbitrum)"),
    output: str = typer.Option(
        "table",
        "--output", "-o",
        help="Output format: table, json, csv",
    ),
    save: Optional[Path] = typer.Option(
        None,
        "--save", "-s",
        help="Save output to file",
    ),
    circulating_supply: Optional[float] = typer.Option(
        None,
        "--circulating-supply", "-c",
        help="Manual override for circulating supply at listing",
    ),
    initial_price: Optional[float] = typer.Option(
        None,
        "--initial-price", "-p",
        help="Manual override for initial price (USD)",
    ),
    listing_date: Optional[str] = typer.Option(
        None,
        "--listing-date", "-d",
        help="Listing date hint (YYYY-MM-DD)",
    ),
    price_method: str = typer.Option(
        "earliest_open",
        "--price-method",
        help="Price selection method: earliest_open, earliest_close, first_hour_vwap",
    ),
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        help="Path to allocation mapping config file",
    ),
    audit: bool = typer.Option(
        False,
        "--audit", "-a",
        help="Include detailed audit trail in output",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Enable verbose logging",
    ),
) -> None:
    """
    Analyze a token's initial listing metrics and allocations.

    Examples:
        token-listing analyze ARB
        token-listing analyze arbitrum --output json
        token-listing analyze OP --circulating-supply 214748364
    """
    setup_logging(verbose)

    # Parse options
    listing_date_dt = None
    if listing_date:
        try:
            listing_date_dt = datetime.strptime(listing_date, "%Y-%m-%d")
        except ValueError:
            console.print(f"[red]Invalid date format: {listing_date}. Use YYYY-MM-DD[/]")
            raise typer.Exit(1)

    try:
        method = PriceSelectionMethod(price_method)
    except ValueError:
        console.print(f"[red]Invalid price method: {price_method}[/]")
        console.print("Valid methods: earliest_open, earliest_close, first_hour_vwap, first_day_vwap")
        raise typer.Exit(1)

    # Initialize orchestrator
    console.print(f"[bold]Analyzing {token}...[/]")

    try:
        orchestrator = TokenListingOrchestrator(
            allocation_config_path=config,
        )

        result = orchestrator.analyze(
            token_identifier=token,
            listing_date_hint=listing_date_dt,
            manual_circulating_supply=circulating_supply,
            manual_initial_price=initial_price,
            price_selection_method=method,
        )

    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        if verbose:
            import traceback
            traceback.print_exc()
        raise typer.Exit(1)

    # Format output
    output_lower = output.lower()
    if output_lower == "json":
        formatter = JSONFormatter()
    elif output_lower == "csv":
        formatter = CSVFormatter()
    else:
        formatter = TableFormatter()

    formatted = formatter.format(result)

    # Display
    if output_lower == "table":
        console.print(formatted)
    else:
        print(formatted)

    # Show audit trail if requested
    if audit:
        console.print("\n")
        audit_formatter = AuditTrailFormatter()
        console.print(audit_formatter.format_summary(result))

    # Save if requested
    if save:
        save.parent.mkdir(parents=True, exist_ok=True)

        if output_lower == "json":
            save_path = save.with_suffix(".json")
        elif output_lower == "csv":
            save_path = save.with_suffix(".csv")
        else:
            save_path = save.with_suffix(".txt")

        formatter.format_to_file(result, str(save_path))
        console.print(f"[green]Saved to {save_path}[/]")

        # Also save audit trail
        if audit:
            audit_path = save_path.with_name(f"{save_path.stem}_audit.txt")
            audit_formatter.format_to_file(result, str(audit_path))
            console.print(f"[green]Audit trail saved to {audit_path}[/]")


@app.command()
def batch(
    tokens_file: Path = typer.Argument(..., help="File with token identifiers (one per line)"),
    output_dir: Path = typer.Option(
        Path("results"),
        "--output-dir", "-o",
        help="Output directory for results",
    ),
    output_format: str = typer.Option(
        "json",
        "--format", "-f",
        help="Output format: json, csv",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Enable verbose logging",
    ),
) -> None:
    """
    Analyze multiple tokens from a file.

    The tokens file should have one token identifier per line.
    Results are saved to the output directory.
    """
    setup_logging(verbose)

    if not tokens_file.exists():
        console.print(f"[red]File not found: {tokens_file}[/]")
        raise typer.Exit(1)

    # Read tokens
    with open(tokens_file, "r") as f:
        tokens = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    if not tokens:
        console.print("[red]No tokens found in file[/]")
        raise typer.Exit(1)

    console.print(f"[bold]Processing {len(tokens)} tokens...[/]")

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Initialize
    orchestrator = TokenListingOrchestrator()

    if output_format == "json":
        formatter = JSONFormatter()
        ext = ".json"
    else:
        formatter = CSVFormatter()
        ext = ".csv"

    # Process each token
    success_count = 0
    for i, token in enumerate(tokens, 1):
        console.print(f"[{i}/{len(tokens)}] Analyzing {token}...")

        try:
            result = orchestrator.analyze(token)

            output_path = output_dir / f"{result.token.coingecko_id}{ext}"
            formatter.format_to_file(result, str(output_path))

            console.print(f"  [green]Saved: {output_path}[/]")
            success_count += 1

        except Exception as e:
            console.print(f"  [red]Failed: {e}[/]")

    console.print(f"\n[bold]Complete: {success_count}/{len(tokens)} successful[/]")


@app.command()
def list_exchanges() -> None:
    """List supported exchanges for price data."""
    from ..providers.price.ccxt_provider import DEFAULT_EXCHANGES

    console.print("[bold]Supported Exchanges:[/]")
    for exchange in DEFAULT_EXCHANGES:
        console.print(f"  - {exchange}")


@app.command()
def version() -> None:
    """Show version information."""
    from .. import __version__
    console.print(f"Token Listing Tool v{__version__}")


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
