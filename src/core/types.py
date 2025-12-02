"""Type definitions and enums for the token listing tool."""

from enum import Enum
from typing import Literal


class CanonicalBucket(str, Enum):
    """Canonical allocation bucket categories."""

    TEAM_FOUNDER = "team_founder"
    ADVISORS_PARTNER = "advisors_partner"
    INVESTORS = "investors"
    PUBLIC_SALES = "public_sales"
    AIRDROP = "airdrop"
    COMMUNITY_REWARDS = "community_rewards"
    LISTING_LIQUIDITY = "listing_liquidity"
    ECOSYSTEM_RD = "ecosystem_rd"
    TREASURY_RESERVE = "treasury_reserve"
    UNKNOWN = "unknown"

    @property
    def display_name(self) -> str:
        """Human-readable display name."""
        names = {
            self.TEAM_FOUNDER: "Team / Founder",
            self.ADVISORS_PARTNER: "Advisors / Partners",
            self.INVESTORS: "Investors",
            self.PUBLIC_SALES: "Public Sales",
            self.AIRDROP: "Airdrop",
            self.COMMUNITY_REWARDS: "Community / Rewards",
            self.LISTING_LIQUIDITY: "Listing / Liquidity",
            self.ECOSYSTEM_RD: "Ecosystem / R&D",
            self.TREASURY_RESERVE: "Treasury / Reserve",
            self.UNKNOWN: "Unknown / Other",
        }
        return names.get(self, self.value)


class DataSource(str, Enum):
    """Data source identifiers."""

    COINGECKO = "coingecko"
    COINMARKETCAP = "coinmarketcap"
    CRYPTORANK = "cryptorank"
    FLIPSIDE = "flipside"
    DROPSTAB = "dropstab"
    TOKENOMIST = "tokenomist"
    MESSARI = "messari"
    ICODROPS = "icodrops"
    CHAINBROKER = "chainbroker"
    TOKENUNLOCKS = "tokenunlocks"
    CCXT = "ccxt"
    MANUAL = "manual"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"


class PriceSelectionMethod(str, Enum):
    """Methods for selecting reference initial price."""

    EARLIEST_OPEN = "earliest_open"       # Open price of earliest candle
    EARLIEST_CLOSE = "earliest_close"     # Close price of earliest candle
    FIRST_HOUR_VWAP = "first_hour_vwap"   # VWAP of first hour of trading
    FIRST_DAY_VWAP = "first_day_vwap"     # VWAP of first day of trading
    MANUAL = "manual"                      # Manually specified price


class ConfidenceLevel(str, Enum):
    """Confidence level for data quality."""

    HIGH = "high"           # Direct from authoritative source, verified
    MEDIUM = "medium"       # From reliable source, not cross-verified
    LOW = "low"             # Estimated or from single unreliable source
    UNKNOWN = "unknown"     # Source unknown or quality unclear


class VestingScheduleType(str, Enum):
    """Types of vesting schedules."""

    LINEAR = "linear"       # Continuous linear unlock
    CLIFF = "cliff"         # Single unlock after cliff period
    STEP = "step"           # Periodic unlocks (monthly, quarterly)
    CUSTOM = "custom"       # Non-standard schedule
    UNKNOWN = "unknown"     # Schedule type not determined


# Type aliases for common patterns
Percentage = float  # 0-100 scale
TokenAmount = float  # Number of tokens
USDAmount = float    # USD value
Timestamp = int      # Unix timestamp in seconds

# Literal types for specific fields
TimeframeType = Literal["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
OutputFormatType = Literal["json", "csv", "table"]
