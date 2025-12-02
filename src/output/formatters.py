"""Output formatters for token listing results.

Provides multiple output formats:
- JSON: Machine-readable, complete data
- CSV: Spreadsheet-compatible, allocation focus
- Table: Human-readable CLI output
"""

import csv
import io
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from ..core.models import TokenListingResult
from ..allocation_mapper.vesting_parser import VestingParser

logger = logging.getLogger(__name__)


class OutputFormatter(ABC):
    """Abstract base class for output formatters."""

    @abstractmethod
    def format(self, result: TokenListingResult) -> str:
        """Format the result as a string."""
        pass

    @abstractmethod
    def format_to_file(self, result: TokenListingResult, filepath: str) -> None:
        """Write formatted result to a file."""
        pass


class JSONFormatter(OutputFormatter):
    """Formats results as JSON."""

    def __init__(self, indent: int = 2, include_raw: bool = False):
        """
        Initialize JSON formatter.

        Args:
            indent: JSON indentation level
            include_raw: Include raw API responses in output
        """
        self.indent = indent
        self.include_raw = include_raw

    def _serialize(self, obj: Any) -> Any:
        """Custom serialization for complex types."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, "model_dump"):
            # Pydantic model
            data = obj.model_dump()
            # Remove raw_response if not including raw
            if not self.include_raw and isinstance(data, dict):
                data.pop("raw_response", None)
            return data
        if hasattr(obj, "value"):
            # Enum
            return obj.value
        return str(obj)

    def format(self, result: TokenListingResult) -> str:
        """Format result as JSON string."""
        data = result.model_dump()

        # Clean up based on settings
        if not self.include_raw:
            self._remove_raw_responses(data)

        return json.dumps(data, default=self._serialize, indent=self.indent)

    def _remove_raw_responses(self, data: dict) -> None:
        """Recursively remove raw_response fields."""
        if isinstance(data, dict):
            data.pop("raw_response", None)
            for value in data.values():
                self._remove_raw_responses(value)
        elif isinstance(data, list):
            for item in data:
                self._remove_raw_responses(item)

    def format_to_file(self, result: TokenListingResult, filepath: str) -> None:
        """Write JSON to file."""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.format(result))


class CSVFormatter(OutputFormatter):
    """Formats allocation data as CSV."""

    def __init__(
        self,
        delimiter: str = ",",
        include_vesting: bool = True,
        include_sources: bool = True,
    ):
        """
        Initialize CSV formatter.

        Args:
            delimiter: CSV delimiter
            include_vesting: Include vesting columns
            include_sources: Include source tracking columns
        """
        self.delimiter = delimiter
        self.include_vesting = include_vesting
        self.include_sources = include_sources
        self.vesting_parser = VestingParser()

    def format(self, result: TokenListingResult) -> str:
        """Format result as CSV string."""
        output = io.StringIO()
        writer = csv.writer(output, delimiter=self.delimiter)

        # Write header sections

        # 1. Token Info Section
        writer.writerow(["# Token Information"])
        writer.writerow(["Field", "Value", "Source"])
        writer.writerow(["Token ID", result.token.coingecko_id, "coingecko"])
        writer.writerow(["Symbol", result.token.symbol, "coingecko"])
        writer.writerow(["Name", result.token.name, "coingecko"])
        writer.writerow(["Categories", "; ".join(result.token.categories or []), "coingecko"])
        writer.writerow([])

        # 2. Initial Listing Section
        writer.writerow(["# Initial Listing Data"])
        if result.reference_price:
            writer.writerow(["Initial Price (USD)", f"${result.reference_price.price_usd:.6f}", result.reference_price.source_exchange])
            writer.writerow(["Listing Timestamp", result.reference_price.timestamp.isoformat(), result.reference_price.source_exchange])
            writer.writerow(["Trading Pair", result.reference_price.source_pair, result.reference_price.source_exchange])
            writer.writerow(["Selection Method", result.reference_price.method.value, ""])
            writer.writerow(["Confidence", result.reference_price.confidence.value, ""])
        else:
            writer.writerow(["Initial Price", "NOT AVAILABLE", ""])
        writer.writerow([])

        # 3. Valuation Section
        writer.writerow(["# Valuation Metrics"])
        if result.valuation:
            v = result.valuation
            writer.writerow(["Initial FDV", f"${v.initial_fdv:,.0f}" if v.initial_fdv else "N/A", f"confidence: {v.fdv_confidence.value}"])
            writer.writerow(["Initial Market Cap", f"${v.initial_market_cap:,.0f}" if v.initial_market_cap else "N/A", f"confidence: {v.market_cap_confidence.value}"])
            writer.writerow(["Total Raised", f"${v.total_raised_usd:,.0f}" if v.total_raised_usd else "N/A", "cryptorank"])
            writer.writerow(["FDV/Raised Ratio", f"{v.fdv_to_raised_ratio:.1f}x" if v.fdv_to_raised_ratio else "N/A", "calculated"])
        writer.writerow([])

        # 4. Supply Section
        writer.writerow(["# Supply Data"])
        if result.supply:
            s = result.supply
            writer.writerow(["Total Supply", f"{s.total_supply:,.0f}" if s.total_supply else "N/A", "coingecko"])
            writer.writerow(["Max Supply", f"{s.max_supply:,.0f}" if s.max_supply else "N/A", "coingecko"])
            writer.writerow(["Circulating (Current)", f"{s.circulating_supply_current:,.0f}" if s.circulating_supply_current else "N/A", "coingecko"])
            writer.writerow(["Circulating (At Listing)", f"{s.circulating_supply_at_listing:,.0f}" if s.circulating_supply_at_listing else "N/A", s.circulating_supply_source.value])
            if s.circulating_supply_is_estimate:
                writer.writerow(["Estimate Method", s.estimation_method or "unknown", ""])
        writer.writerow([])

        # 5. Allocation Table Section
        writer.writerow(["# Token Allocation"])

        # Build header
        header = ["Canonical Bucket", "Display Name", "Percentage", "Original Labels"]
        if self.include_sources:
            header.append("Sources")
        if self.include_vesting:
            header.extend(["TGE Unlock %", "Cliff (months)", "Vesting (months)", "Schedule", "Vesting Notes"])

        writer.writerow(header)

        if result.allocations:
            for alloc in result.allocations.mapped_allocations:
                row = [
                    alloc.canonical_bucket.value,
                    alloc.display_name,
                    f"{alloc.percentage:.2f}%" if alloc.percentage else "N/A",
                    "; ".join(alloc.original_labels),
                ]

                if self.include_sources:
                    row.append("; ".join(s.value for s in alloc.sources))

                if self.include_vesting:
                    if alloc.vesting:
                        v = alloc.vesting
                        row.extend([
                            f"{v.tge_unlock_pct:.1f}%" if v.tge_unlock_pct else "",
                            str(v.cliff_months) if v.cliff_months else "",
                            str(v.vesting_months) if v.vesting_months else "",
                            v.schedule_type.value if v.schedule_type else "",
                            v.raw_description or "",
                        ])
                    else:
                        row.extend(["", "", "", "", ""])

                writer.writerow(row)

            # Add totals row
            writer.writerow([])
            writer.writerow([
                "TOTAL",
                "",
                f"{result.allocations.total_percentage:.2f}%" if result.allocations.total_percentage else "N/A",
                f"Complete: {result.allocations.is_complete}",
            ])

        # 6. Conflicts Section (if any)
        if result.allocations and result.allocations.conflicts:
            writer.writerow([])
            writer.writerow(["# Allocation Conflicts"])
            writer.writerow(["Bucket", "Discrepancy", "Sources", "Values"])
            for conflict in result.allocations.conflicts:
                writer.writerow([
                    conflict.canonical_bucket.value,
                    f"{conflict.discrepancy_pct:.1f}%",
                    "; ".join(s.value for s in conflict.sources_involved),
                    "; ".join(f"{k}={v:.1f}%" for k, v in conflict.values.items()),
                ])

        # 7. Data Quality Flags
        if result.quality_flags:
            writer.writerow([])
            writer.writerow(["# Data Quality Flags"])
            writer.writerow(["Field", "Issue", "Severity"])
            for flag in result.quality_flags:
                writer.writerow([flag.field, flag.issue, flag.severity])

        return output.getvalue()

    def format_to_file(self, result: TokenListingResult, filepath: str) -> None:
        """Write CSV to file."""
        with open(filepath, "w", encoding="utf-8", newline="") as f:
            f.write(self.format(result))


class TableFormatter(OutputFormatter):
    """Formats results as human-readable tables for CLI output."""

    def __init__(self, use_rich: bool = True, width: int = 100):
        """
        Initialize table formatter.

        Args:
            use_rich: Use rich library for colored output (if available)
            width: Maximum table width
        """
        self.use_rich = use_rich
        self.width = width
        self.vesting_parser = VestingParser()

        # Try to import rich
        self._rich_available = False
        if use_rich:
            try:
                from rich.console import Console
                from rich.table import Table
                self._rich_available = True
            except ImportError:
                pass

    def format(self, result: TokenListingResult) -> str:
        """Format result as readable tables."""
        if self._rich_available:
            return self._format_rich(result)
        return self._format_plain(result)

    def _format_plain(self, result: TokenListingResult) -> str:
        """Plain text formatting without rich."""
        lines = []
        sep = "=" * 60

        # Header
        lines.append(sep)
        lines.append(f"  TOKEN LISTING ANALYSIS: {result.token.symbol}")
        lines.append(f"  {result.token.name} ({result.token.coingecko_id})")
        lines.append(sep)
        lines.append("")

        # Initial Price
        lines.append("INITIAL LISTING PRICE")
        lines.append("-" * 40)
        if result.reference_price:
            rp = result.reference_price
            lines.append(f"  Price:     ${rp.price_usd:.6f}")
            lines.append(f"  Timestamp: {rp.timestamp.strftime('%Y-%m-%d %H:%M UTC')}")
            lines.append(f"  Exchange:  {rp.source_exchange}")
            lines.append(f"  Pair:      {rp.source_pair}")
            lines.append(f"  Method:    {rp.method.value}")
            lines.append(f"  Confidence: {rp.confidence.value}")
        else:
            lines.append("  NOT AVAILABLE")
        lines.append("")

        # Valuation Metrics
        lines.append("VALUATION METRICS")
        lines.append("-" * 40)
        if result.valuation:
            v = result.valuation
            lines.append(f"  Initial FDV:      ${v.initial_fdv:>15,.0f}" if v.initial_fdv else "  Initial FDV:      N/A")
            lines.append(f"  Initial MCap:     ${v.initial_market_cap:>15,.0f}" if v.initial_market_cap else "  Initial MCap:     N/A (circulating supply unknown)")
            lines.append(f"  Total Raised:     ${v.total_raised_usd:>15,.0f}" if v.total_raised_usd else "  Total Raised:     N/A")
            lines.append(f"  FDV/Raised:       {v.fdv_to_raised_ratio:>15.1f}x" if v.fdv_to_raised_ratio else "  FDV/Raised:       N/A")
        lines.append("")

        # Supply
        lines.append("SUPPLY DATA")
        lines.append("-" * 40)
        if result.supply:
            s = result.supply
            lines.append(f"  Total Supply:     {s.total_supply:>18,.0f}" if s.total_supply else "  Total Supply:     N/A")
            lines.append(f"  Max Supply:       {s.max_supply:>18,.0f}" if s.max_supply else "  Max Supply:       N/A")
            lines.append(f"  Circulating Now:  {s.circulating_supply_current:>18,.0f}" if s.circulating_supply_current else "")
            if s.circulating_supply_at_listing:
                est_marker = " (est)" if s.circulating_supply_is_estimate else ""
                lines.append(f"  Circ at Listing:  {s.circulating_supply_at_listing:>18,.0f}{est_marker}")
            else:
                lines.append("  Circ at Listing:  UNKNOWN - provide manual override")
        lines.append("")

        # Allocations
        lines.append("TOKEN ALLOCATION")
        lines.append("-" * 40)
        if result.allocations and result.allocations.mapped_allocations:
            lines.append(f"  {'Bucket':<25} {'%':>8}  {'Vesting':<30}")
            lines.append("  " + "-" * 65)
            for alloc in result.allocations.mapped_allocations:
                pct = f"{alloc.percentage:.1f}%" if alloc.percentage else "N/A"
                vesting = self.vesting_parser.format_summary(alloc.vesting)
                lines.append(f"  {alloc.display_name:<25} {pct:>8}  {vesting:<30}")

            lines.append("  " + "-" * 65)
            total_pct = f"{result.allocations.total_percentage:.1f}%" if result.allocations.total_percentage else "N/A"
            complete = "Complete" if result.allocations.is_complete else "Incomplete"
            lines.append(f"  {'TOTAL':<25} {total_pct:>8}  ({complete})")
        else:
            lines.append("  No allocation data available")
        lines.append("")

        # Conflicts
        if result.allocations and result.allocations.conflicts:
            lines.append("ALLOCATION CONFLICTS")
            lines.append("-" * 40)
            for c in result.allocations.conflicts:
                lines.append(f"  {c.canonical_bucket.display_name}: {c.discrepancy_pct:.1f}% discrepancy")
                for src, val in c.values.items():
                    lines.append(f"    - {src}: {val:.1f}%")
            lines.append("")

        # Quality Flags
        if result.quality_flags:
            lines.append("DATA QUALITY FLAGS")
            lines.append("-" * 40)
            for flag in result.quality_flags:
                lines.append(f"  [{flag.severity.upper()}] {flag.field}: {flag.issue}")
            lines.append("")

        # Footer
        lines.append(sep)
        lines.append(f"  Analysis timestamp: {result.analysis_timestamp.strftime('%Y-%m-%d %H:%M UTC')}")
        lines.append(f"  Sources: {', '.join(e.source.value for e in result.audit_trail[:5])}")
        lines.append(sep)

        return "\n".join(lines)

    def _format_rich(self, result: TokenListingResult) -> str:
        """Rich library formatting with colors."""
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        from rich.text import Text
        from io import StringIO

        output = StringIO()
        console = Console(file=output, force_terminal=True, width=self.width)

        # Title
        console.print(Panel(
            f"[bold cyan]{result.token.symbol}[/] - {result.token.name}\n"
            f"[dim]CoinGecko ID: {result.token.coingecko_id}[/]",
            title="Token Listing Analysis",
            expand=False,
        ))

        # Initial Price Table
        if result.reference_price:
            rp = result.reference_price
            price_table = Table(title="Initial Listing Price", show_header=False)
            price_table.add_column("Field", style="cyan")
            price_table.add_column("Value", style="green")
            price_table.add_row("Price", f"${rp.price_usd:.6f}")
            price_table.add_row("Timestamp", rp.timestamp.strftime("%Y-%m-%d %H:%M UTC"))
            price_table.add_row("Exchange", rp.source_exchange)
            price_table.add_row("Pair", rp.source_pair)
            price_table.add_row("Confidence", rp.confidence.value)
            console.print(price_table)

        # Valuation Table
        if result.valuation:
            v = result.valuation
            val_table = Table(title="Valuation Metrics", show_header=False)
            val_table.add_column("Metric", style="cyan")
            val_table.add_column("Value", style="green")
            val_table.add_column("Confidence", style="dim")

            if v.initial_fdv:
                val_table.add_row("Initial FDV", f"${v.initial_fdv:,.0f}", v.fdv_confidence.value)
            if v.initial_market_cap:
                val_table.add_row("Initial MCap", f"${v.initial_market_cap:,.0f}", v.market_cap_confidence.value)
            else:
                val_table.add_row("Initial MCap", "[yellow]Unknown[/]", "Need circulating supply")
            if v.total_raised_usd:
                val_table.add_row("Total Raised", f"${v.total_raised_usd:,.0f}", "")
            if v.fdv_to_raised_ratio:
                val_table.add_row("FDV/Raised", f"{v.fdv_to_raised_ratio:.1f}x", "")

            console.print(val_table)

        # Allocation Table
        if result.allocations and result.allocations.mapped_allocations:
            alloc_table = Table(title="Token Allocation")
            alloc_table.add_column("Category", style="cyan")
            alloc_table.add_column("%", justify="right", style="green")
            alloc_table.add_column("Vesting", style="dim")
            alloc_table.add_column("Source", style="dim")

            for alloc in result.allocations.mapped_allocations:
                pct = f"{alloc.percentage:.1f}%" if alloc.percentage else "-"
                vesting = self.vesting_parser.format_summary(alloc.vesting)
                sources = ", ".join(s.value for s in alloc.sources)
                alloc_table.add_row(alloc.display_name, pct, vesting, sources)

            # Total row
            total_pct = f"{result.allocations.total_percentage:.1f}%" if result.allocations.total_percentage else "N/A"
            status = "[green]Complete[/]" if result.allocations.is_complete else "[yellow]Incomplete[/]"
            alloc_table.add_row("", "", "", "", end_section=True)
            alloc_table.add_row("[bold]TOTAL[/]", f"[bold]{total_pct}[/]", status, "")

            console.print(alloc_table)

        # Quality flags
        if result.quality_flags:
            console.print("\n[bold yellow]Data Quality Flags:[/]")
            for flag in result.quality_flags:
                icon = "!" if flag.severity == "warning" else "i"
                console.print(f"  [{icon}] {flag.field}: {flag.issue}")

        return output.getvalue()

    def format_to_file(self, result: TokenListingResult, filepath: str) -> None:
        """Write formatted output to file."""
        # For file output, use plain format (no ANSI codes)
        old_rich = self._rich_available
        self._rich_available = False
        content = self.format(result)
        self._rich_available = old_rich

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
