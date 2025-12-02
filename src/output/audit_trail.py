"""Audit trail formatter for transparency and reproducibility.

Generates detailed audit documentation showing:
- All data sources consulted
- API calls made and their status
- Estimation methods used
- Mapping rules applied
- Data quality issues detected
"""

import logging
from datetime import datetime
from typing import Any

from ..core.models import TokenListingResult

logger = logging.getLogger(__name__)


class AuditTrailFormatter:
    """Formats audit trail information for transparency."""

    def format_summary(self, result: TokenListingResult) -> str:
        """
        Format a summary of the audit trail.

        Args:
            result: TokenListingResult with audit data

        Returns:
            Formatted string summary
        """
        lines = []
        lines.append("=" * 70)
        lines.append("AUDIT TRAIL SUMMARY")
        lines.append("=" * 70)
        lines.append("")

        # Analysis metadata
        lines.append(f"Analysis Timestamp: {result.analysis_timestamp.isoformat()}")
        lines.append(f"Tool Version: {result.tool_version}")
        lines.append(f"Token: {result.token.symbol} ({result.token.coingecko_id})")
        lines.append("")

        # Data Sources Used
        lines.append("DATA SOURCES CONSULTED")
        lines.append("-" * 40)
        sources_summary = self._summarize_sources(result)
        for source, info in sources_summary.items():
            status = "OK" if info["success_count"] > 0 else "FAILED"
            lines.append(f"  {source}: {status}")
            lines.append(f"    - Calls: {info['total_count']} ({info['success_count']} successful)")
            if info.get("endpoints"):
                for endpoint in info["endpoints"][:3]:
                    lines.append(f"    - Endpoint: {endpoint}")
        lines.append("")

        # Price Source
        lines.append("INITIAL PRICE SOURCE")
        lines.append("-" * 40)
        if result.reference_price:
            rp = result.reference_price
            lines.append(f"  Exchange: {rp.source_exchange}")
            lines.append(f"  Pair: {rp.source_pair}")
            lines.append(f"  Selection Method: {rp.method.value}")
            lines.append(f"  Confidence: {rp.confidence.value}")
            if rp.notes:
                lines.append(f"  Notes: {rp.notes}")
        else:
            lines.append("  NOT AVAILABLE - no valid price data found")
        lines.append("")

        # Supply Estimation
        lines.append("SUPPLY DATA")
        lines.append("-" * 40)
        if result.supply:
            s = result.supply
            lines.append(f"  Total Supply Source: {s.source.source.value if s.source else 'unknown'}")
            lines.append(f"  Circulating at Listing: {s.circulating_supply_source.value}")
            if s.circulating_supply_is_estimate:
                lines.append(f"  ESTIMATE METHOD: {s.estimation_method}")
            else:
                lines.append("  Circulating supply is VERIFIED (not estimated)")
        lines.append("")

        # Allocation Mapping
        lines.append("ALLOCATION MAPPING")
        lines.append("-" * 40)
        if result.allocations:
            a = result.allocations
            lines.append(f"  Sources: {', '.join(s.value for s in a.sources_used)}")
            lines.append(f"  Raw allocations: {len(a.raw_allocations)}")
            lines.append(f"  Mapped buckets: {len(a.mapped_allocations)}")
            lines.append(f"  Conflicts detected: {len(a.conflicts)}")
            lines.append(f"  Total percentage: {a.total_percentage:.1f}%" if a.total_percentage else "")
            lines.append(f"  Complete (95-105%): {a.is_complete}")

            if a.conflicts:
                lines.append("")
                lines.append("  CONFLICTS:")
                for conflict in a.conflicts:
                    lines.append(f"    - {conflict.canonical_bucket.value}: {conflict.discrepancy_pct:.1f}% discrepancy")
                    for src, val in conflict.values.items():
                        lines.append(f"      {src}: {val:.1f}%")
        lines.append("")

        # Quality Flags
        if result.quality_flags:
            lines.append("DATA QUALITY FLAGS")
            lines.append("-" * 40)
            for flag in result.quality_flags:
                lines.append(f"  [{flag.severity.upper()}] {flag.field}")
                lines.append(f"    Issue: {flag.issue}")
                if flag.suggestion:
                    lines.append(f"    Suggestion: {flag.suggestion}")
            lines.append("")

        # Detailed Audit Trail
        lines.append("DETAILED API CALLS")
        lines.append("-" * 40)
        for entry in result.audit_trail:
            status = "OK" if entry.success else "FAILED"
            duration = f"{entry.duration_ms}ms" if entry.duration_ms else "N/A"
            lines.append(f"  [{entry.timestamp.strftime('%H:%M:%S')}] {entry.source.value} {entry.action}")
            lines.append(f"    Endpoint: {entry.endpoint or 'N/A'}")
            lines.append(f"    Status: {status}, Duration: {duration}")
            if entry.error_message:
                lines.append(f"    Error: {entry.error_message}")
            if entry.notes:
                lines.append(f"    Notes: {entry.notes}")
        lines.append("")

        lines.append("=" * 70)
        lines.append("END OF AUDIT TRAIL")
        lines.append("=" * 70)

        return "\n".join(lines)

    def _summarize_sources(self, result: TokenListingResult) -> dict[str, Any]:
        """Summarize source usage from audit trail."""
        summary: dict[str, dict[str, Any]] = {}

        for entry in result.audit_trail:
            source_name = entry.source.value
            if source_name not in summary:
                summary[source_name] = {
                    "total_count": 0,
                    "success_count": 0,
                    "endpoints": [],
                }

            summary[source_name]["total_count"] += 1
            if entry.success:
                summary[source_name]["success_count"] += 1
            if entry.endpoint and entry.endpoint not in summary[source_name]["endpoints"]:
                summary[source_name]["endpoints"].append(entry.endpoint)

        return summary

    def format_estimation_methods(self, result: TokenListingResult) -> str:
        """
        Format details about estimation methods used.

        Args:
            result: TokenListingResult

        Returns:
            Formatted explanation of estimates
        """
        lines = []
        lines.append("ESTIMATION METHODS USED")
        lines.append("=" * 50)
        lines.append("")

        estimates_found = False

        # Circulating supply estimation
        if result.supply and result.supply.circulating_supply_is_estimate:
            estimates_found = True
            lines.append("1. CIRCULATING SUPPLY AT LISTING")
            lines.append("-" * 40)
            lines.append(f"   Status: ESTIMATED")
            lines.append(f"   Method: {result.supply.estimation_method}")
            if result.supply.circulating_supply_at_listing:
                lines.append(f"   Value: {result.supply.circulating_supply_at_listing:,.0f} tokens")
            lines.append("")
            lines.append("   IMPACT: Initial Market Cap calculation uses this estimate.")
            lines.append("   For accurate Market Cap, provide manual_circulating_supply.")
            lines.append("")

        # Market cap confidence
        if result.valuation and result.valuation.market_cap_confidence.value in ("low", "unknown"):
            estimates_found = True
            lines.append("2. INITIAL MARKET CAP")
            lines.append("-" * 40)
            lines.append(f"   Confidence: {result.valuation.market_cap_confidence.value.upper()}")
            lines.append("   Reason: Circulating supply at listing is estimated or unknown")
            lines.append("")

        # Price selection notes
        if result.reference_price and result.reference_price.notes:
            estimates_found = True
            lines.append("3. PRICE SELECTION")
            lines.append("-" * 40)
            lines.append(f"   Notes: {result.reference_price.notes}")
            lines.append("")

        if not estimates_found:
            lines.append("No estimation methods were required for this analysis.")
            lines.append("All values are from primary sources.")

        return "\n".join(lines)

    def generate_reproducibility_script(self, result: TokenListingResult) -> str:
        """
        Generate a Python script that reproduces the analysis.

        Args:
            result: TokenListingResult

        Returns:
            Python script as string
        """
        script_lines = [
            '"""',
            f"Reproducibility script for {result.token.symbol} analysis",
            f"Generated: {result.analysis_timestamp.isoformat()}",
            f"Tool Version: {result.tool_version}",
            '"""',
            "",
            "from token_listing_tool.orchestrator import TokenListingOrchestrator",
            "",
            "# Initialize orchestrator",
            "orchestrator = TokenListingOrchestrator()",
            "",
            f"# Analyze {result.token.symbol}",
            f'result = orchestrator.analyze("{result.token.coingecko_id}")',
            "",
            "# Print results",
            "from token_listing_tool.output import TableFormatter",
            "formatter = TableFormatter()",
            "print(formatter.format(result))",
        ]

        return "\n".join(script_lines)

    def format_to_file(self, result: TokenListingResult, filepath: str) -> None:
        """Write audit trail to file."""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.format_summary(result))
            f.write("\n\n")
            f.write(self.format_estimation_methods(result))
