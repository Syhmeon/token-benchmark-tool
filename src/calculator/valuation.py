"""Valuation calculator for computing FDV, Market Cap, and related metrics.

All calculations use explicit formulas:
- Market Cap = circulating_supply × price
- FDV = fully_diluted_supply × price
- FDV/Raised ratio = FDV / total_raised
"""

import logging
from typing import Any

from ..core.models import (
    FundraisingData,
    ReferencePrice,
    SupplyData,
    ValuationMetrics,
)
from ..core.types import ConfidenceLevel

logger = logging.getLogger(__name__)


class ValuationCalculator:
    """Calculates valuation metrics from price and supply data."""

    def calculate(
        self,
        reference_price: ReferencePrice,
        supply_data: SupplyData,
        fundraising_data: FundraisingData | None = None,
    ) -> ValuationMetrics:
        """
        Calculate valuation metrics.

        Args:
            reference_price: The reference initial price
            supply_data: Token supply data
            fundraising_data: Optional fundraising data

        Returns:
            ValuationMetrics with calculated values
        """
        price = reference_price.price_usd
        notes: list[str] = []

        # Calculate FDV
        initial_fdv = None
        fdv_confidence = ConfidenceLevel.UNKNOWN

        fully_diluted_supply = supply_data.fully_diluted_supply
        if fully_diluted_supply and price:
            initial_fdv = fully_diluted_supply * price
            fdv_confidence = ConfidenceLevel.HIGH
            notes.append(
                f"FDV = {fully_diluted_supply:,.0f} tokens × ${price:.6f} = ${initial_fdv:,.0f}"
            )

            # Note which supply was used
            if supply_data.max_supply and supply_data.max_supply == fully_diluted_supply:
                notes.append("Using max_supply for FDV calculation")
            else:
                notes.append("Using total_supply for FDV calculation")
        else:
            notes.append("FDV could not be calculated: missing supply or price data")

        # Calculate Market Cap
        initial_market_cap = None
        mcap_confidence = ConfidenceLevel.UNKNOWN

        circ_supply = supply_data.circulating_supply_at_listing
        if circ_supply and price:
            initial_market_cap = circ_supply * price
            notes.append(
                f"Market Cap = {circ_supply:,.0f} tokens × ${price:.6f} = ${initial_market_cap:,.0f}"
            )

            # Set confidence based on supply source
            if supply_data.circulating_supply_is_estimate:
                mcap_confidence = ConfidenceLevel.LOW
                notes.append(
                    f"WARNING: Circulating supply at listing is ESTIMATED. "
                    f"Method: {supply_data.estimation_method or 'unknown'}"
                )
            else:
                mcap_confidence = ConfidenceLevel.HIGH
        else:
            notes.append(
                "Market Cap could not be calculated: circulating supply at listing is unknown. "
                "Provide manual_circulating_supply for accurate calculation."
            )

        # Calculate FDV/Raised ratio
        total_raised = fundraising_data.total_raised_usd if fundraising_data else None
        fdv_to_raised_ratio = None

        if initial_fdv and total_raised and total_raised > 0:
            fdv_to_raised_ratio = initial_fdv / total_raised
            notes.append(
                f"FDV/Raised = ${initial_fdv:,.0f} / ${total_raised:,.0f} = {fdv_to_raised_ratio:.1f}x"
            )
        elif initial_fdv and not total_raised:
            notes.append("FDV/Raised ratio not available: no fundraising data")

        return ValuationMetrics(
            initial_price_usd=price,
            initial_market_cap=initial_market_cap,
            initial_fdv=initial_fdv,
            total_raised_usd=total_raised,
            fdv_to_raised_ratio=fdv_to_raised_ratio,
            market_cap_confidence=mcap_confidence,
            fdv_confidence=fdv_confidence,
            calculation_notes=notes,
        )

    def calculate_with_manual_override(
        self,
        reference_price: ReferencePrice,
        supply_data: SupplyData,
        fundraising_data: FundraisingData | None = None,
        manual_circulating_supply: float | None = None,
        manual_total_supply: float | None = None,
    ) -> ValuationMetrics:
        """
        Calculate valuation metrics with optional manual overrides.

        Args:
            reference_price: The reference initial price
            supply_data: Token supply data
            fundraising_data: Optional fundraising data
            manual_circulating_supply: Override circulating supply at listing
            manual_total_supply: Override total supply

        Returns:
            ValuationMetrics with calculated values
        """
        # Create modified supply data with overrides
        if manual_circulating_supply is not None or manual_total_supply is not None:
            supply_data = SupplyData(
                total_supply=manual_total_supply or supply_data.total_supply,
                max_supply=supply_data.max_supply,
                circulating_supply_current=supply_data.circulating_supply_current,
                circulating_supply_at_listing=(
                    manual_circulating_supply
                    if manual_circulating_supply is not None
                    else supply_data.circulating_supply_at_listing
                ),
                circulating_supply_source=supply_data.circulating_supply_source,
                circulating_supply_is_estimate=(
                    False if manual_circulating_supply is not None
                    else supply_data.circulating_supply_is_estimate
                ),
                estimation_method=(
                    "Manual override provided"
                    if manual_circulating_supply is not None
                    else supply_data.estimation_method
                ),
                source=supply_data.source,
            )

        return self.calculate(reference_price, supply_data, fundraising_data)


def calc_fdv(total_supply: float, price: float) -> float:
    """
    Calculate Fully Diluted Valuation.

    Formula: FDV = total_supply × price

    Args:
        total_supply: Total or max token supply
        price: Token price in USD

    Returns:
        FDV in USD
    """
    return total_supply * price


def calc_market_cap(circulating_supply: float, price: float) -> float:
    """
    Calculate Market Capitalization.

    Formula: Market Cap = circulating_supply × price

    Args:
        circulating_supply: Circulating token supply
        price: Token price in USD

    Returns:
        Market cap in USD
    """
    return circulating_supply * price


def calc_fdv_to_raised(fdv: float, total_raised: float) -> float:
    """
    Calculate FDV to Total Raised ratio.

    Formula: Ratio = FDV / total_raised

    Args:
        fdv: Fully Diluted Valuation in USD
        total_raised: Total funds raised in USD

    Returns:
        Ratio (e.g., 10.0 means 10x)
    """
    if total_raised <= 0:
        raise ValueError("total_raised must be positive")
    return fdv / total_raised


def calc_circulating_from_allocation(
    total_supply: float,
    allocation_pct: float,
    tge_unlock_pct: float,
) -> float:
    """
    Estimate circulating supply from a single allocation's TGE unlock.

    This is a simplified calculation for a single allocation category.
    For accurate total circulating, sum across all allocations.

    Formula: unlocked_tokens = total_supply × (allocation_pct/100) × (tge_unlock_pct/100)

    Args:
        total_supply: Total token supply
        allocation_pct: This allocation's percentage of total (0-100)
        tge_unlock_pct: Percentage unlocked at TGE (0-100)

    Returns:
        Number of tokens unlocked from this allocation
    """
    return total_supply * (allocation_pct / 100) * (tge_unlock_pct / 100)
