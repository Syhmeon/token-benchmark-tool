"""Pydantic data models for the token listing tool.

All data structures are immutable (frozen) after creation to ensure
data integrity throughout the pipeline.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from .types import (
    CanonicalBucket,
    ConfidenceLevel,
    DataSource,
    Percentage,
    PriceSelectionMethod,
    TimeframeType,
    TokenAmount,
    USDAmount,
    VestingScheduleType,
)


class SourceReference(BaseModel):
    """Reference to the data source for audit trail."""

    source: DataSource
    url: str | None = None
    endpoint: str | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    raw_response: dict[str, Any] | None = Field(default=None, exclude=True)

    model_config = {"frozen": True}


class TokenInfo(BaseModel):
    """Basic token information resolved from user input."""

    coingecko_id: str
    symbol: str
    name: str
    contract_addresses: dict[str, str] = Field(default_factory=dict)  # chain -> address
    categories: list[str] = Field(default_factory=list)
    genesis_date: datetime | None = None
    source: SourceReference | None = None

    model_config = {"frozen": True}


class ExchangeCandle(BaseModel):
    """OHLCV candle data from an exchange."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    volume_usd: float | None = None  # Volume in USD if calculable

    model_config = {"frozen": True}

    @property
    def is_valid(self) -> bool:
        """Check if candle has valid non-zero values."""
        return (
            self.open > 0
            and self.high > 0
            and self.low > 0
            and self.close > 0
            and self.high >= self.low
        )


class ExchangeListing(BaseModel):
    """Listing data from a specific exchange."""

    exchange: str
    trading_pair: str
    base_currency: str
    quote_currency: str
    first_candle: ExchangeCandle | None = None
    timeframe: TimeframeType = "1h"
    source: SourceReference | None = None
    error: str | None = None  # If fetching failed

    model_config = {"frozen": True}

    @property
    def has_data(self) -> bool:
        """Check if we successfully retrieved listing data."""
        return self.first_candle is not None and self.error is None


class ReferencePrice(BaseModel):
    """The selected reference price for initial valuation."""

    price_usd: float
    timestamp: datetime
    method: PriceSelectionMethod
    source_exchange: str
    source_pair: str
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    notes: str | None = None

    model_config = {"frozen": True}


class SupplyData(BaseModel):
    """Token supply information."""

    total_supply: TokenAmount | None = None
    max_supply: TokenAmount | None = None
    circulating_supply_current: TokenAmount | None = None
    circulating_supply_at_listing: TokenAmount | None = None
    circulating_supply_source: DataSource = DataSource.UNKNOWN
    circulating_supply_is_estimate: bool = True
    estimation_method: str | None = None
    source: SourceReference | None = None

    model_config = {"frozen": True}

    @property
    def fully_diluted_supply(self) -> TokenAmount | None:
        """Return the supply to use for FDV calculation (max or total)."""
        return self.max_supply if self.max_supply else self.total_supply


class FundraisingRound(BaseModel):
    """A single fundraising round."""

    round_name: str
    amount_usd: USDAmount | None = None
    date: datetime | None = None
    valuation_usd: USDAmount | None = None
    token_price: float | None = None
    tokens_sold: TokenAmount | None = None
    investors: list[str] = Field(default_factory=list)
    lead_investors: list[str] = Field(default_factory=list)

    model_config = {"frozen": True}


class FundraisingData(BaseModel):
    """Complete fundraising information for a token."""

    total_raised_usd: USDAmount | None = None
    rounds: list[FundraisingRound] = Field(default_factory=list)
    source: SourceReference | None = None

    model_config = {"frozen": True}


class VestingTerms(BaseModel):
    """Vesting schedule details for an allocation."""

    tge_unlock_pct: Percentage | None = None  # Percentage unlocked at TGE
    cliff_months: int | None = None
    vesting_months: int | None = None  # Total vesting duration
    schedule_type: VestingScheduleType = VestingScheduleType.UNKNOWN
    unlock_frequency: str | None = None  # "monthly", "quarterly", etc.
    start_date: datetime | None = None
    end_date: datetime | None = None
    raw_description: str | None = None  # Original vesting text
    notes: str | None = None

    model_config = {"frozen": True}

    @property
    def has_details(self) -> bool:
        """Check if any vesting details are available."""
        return any(
            [
                self.tge_unlock_pct is not None,
                self.cliff_months is not None,
                self.vesting_months is not None,
            ]
        )


class RawAllocation(BaseModel):
    """Raw allocation data as reported by a source (before mapping)."""

    source: DataSource
    label: str  # Original label from source
    percentage: Percentage | None = None
    amount: TokenAmount | None = None
    vesting: VestingTerms | None = None
    source_reference: SourceReference | None = None

    model_config = {"frozen": True}

    @field_validator("percentage")
    @classmethod
    def validate_percentage(cls, v: Percentage | None) -> Percentage | None:
        if v is not None and (v < 0 or v > 100):
            raise ValueError(f"Percentage must be 0-100, got {v}")
        return v


class MappedAllocation(BaseModel):
    """Allocation mapped to a canonical bucket."""

    canonical_bucket: CanonicalBucket
    display_name: str  # Human-readable bucket name
    original_labels: list[str]  # All original labels that mapped here
    percentage: Percentage | None = None
    amount: TokenAmount | None = None
    sources: list[DataSource] = Field(default_factory=list)
    vesting: VestingTerms | None = None
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    mapping_rule: str | None = None  # Which rule triggered the mapping

    model_config = {"frozen": True}


class AllocationConflict(BaseModel):
    """Records a conflict between sources for the same allocation bucket."""

    canonical_bucket: CanonicalBucket
    sources_involved: list[DataSource]
    values: dict[str, Percentage]  # source -> percentage
    discrepancy_pct: Percentage
    resolution: str | None = None  # How it was resolved, if at all
    preferred_source: DataSource | None = None

    model_config = {"frozen": True}


class AllocationData(BaseModel):
    """Complete allocation data with raw, mapped, and conflict information."""

    raw_allocations: list[RawAllocation] = Field(default_factory=list)
    mapped_allocations: list[MappedAllocation] = Field(default_factory=list)
    conflicts: list[AllocationConflict] = Field(default_factory=list)
    total_percentage: Percentage | None = None  # Sum of mapped percentages
    is_complete: bool = False  # Whether allocations sum to ~100%
    sources_used: list[DataSource] = Field(default_factory=list)

    model_config = {"frozen": True}


class ValuationMetrics(BaseModel):
    """Calculated valuation metrics at initial listing."""

    initial_price_usd: float
    initial_market_cap: USDAmount | None = None
    initial_fdv: USDAmount | None = None
    total_raised_usd: USDAmount | None = None
    fdv_to_raised_ratio: float | None = None
    market_cap_confidence: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    fdv_confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    calculation_notes: list[str] = Field(default_factory=list)

    model_config = {"frozen": True}


class AuditEntry(BaseModel):
    """Audit trail entry for a data fetch or calculation."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    source: DataSource
    action: str  # "fetch", "calculate", "estimate", "map"
    endpoint: str | None = None
    success: bool = True
    error_message: str | None = None
    duration_ms: int | None = None
    notes: str | None = None

    model_config = {"frozen": True}


class DataQualityFlag(BaseModel):
    """Flag indicating a data quality issue."""

    field: str
    issue: str
    severity: str = "warning"  # "info", "warning", "error"
    suggestion: str | None = None

    model_config = {"frozen": True}


class TokenListingResult(BaseModel):
    """Complete result of the token listing analysis."""

    # Token identification
    token: TokenInfo

    # Listing data
    exchange_listings: list[ExchangeListing] = Field(default_factory=list)
    reference_price: ReferencePrice | None = None

    # Supply data
    supply: SupplyData | None = None

    # Valuation metrics
    valuation: ValuationMetrics | None = None

    # Fundraising
    fundraising: FundraisingData | None = None

    # Allocations
    allocations: AllocationData | None = None

    # Peer information
    peer_tokens: list[str] = Field(default_factory=list)  # CoinGecko IDs

    # Audit trail
    audit_trail: list[AuditEntry] = Field(default_factory=list)
    quality_flags: list[DataQualityFlag] = Field(default_factory=list)

    # Metadata
    analysis_timestamp: datetime = Field(default_factory=datetime.utcnow)
    tool_version: str = "0.1.0"

    model_config = {"frozen": True}

    def add_quality_flag(
        self, field: str, issue: str, severity: str = "warning"
    ) -> "TokenListingResult":
        """Create a new result with an added quality flag (immutable pattern)."""
        new_flags = list(self.quality_flags)
        new_flags.append(DataQualityFlag(field=field, issue=issue, severity=severity))
        return self.model_copy(update={"quality_flags": new_flags})
