# Token Listing FDV and Allocation Benchmark Tool

A production-grade internal tool for tokenomics analysts to analyze initial token listings, compute FDV/market cap metrics, and map token allocations to canonical buckets.

## Features

- **Initial Listing Price Discovery**: Fetches first listing candles from multiple exchanges via CCXT
- **Valuation Metrics**: Computes Initial FDV and Market Cap with explicit formulas
- **Fundraising Data**: Retrieves total raised and funding rounds from CryptoRank
- **Allocation Mapping**: Maps raw allocation labels to canonical buckets with configurable rules
- **Vesting Parsing**: Extracts and structures vesting schedules from free-text descriptions
- **Full Auditability**: Tracks all data sources, estimation methods, and quality flags
- **Multiple Output Formats**: JSON, CSV, and rich CLI tables

## Installation

```bash
# Clone the repository
cd token_listing_tool

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install the package
pip install -e .
```

## Quick Start

### CLI Usage

```bash
# Basic analysis
python -m cli.main analyze ARB

# With manual circulating supply override
python -m cli.main analyze ARB --circulating-supply 1275000000

# Output as JSON
python -m cli.main analyze ARB --output json --save results/arb.json

# With audit trail
python -m cli.main analyze ARB --audit --verbose
```

### Python API

```python
from src.orchestrator import TokenListingOrchestrator
from src.output.formatters import TableFormatter
from datetime import datetime, timezone

# Initialize
orchestrator = TokenListingOrchestrator()

# Analyze a token
result = orchestrator.analyze(
    token_identifier="arbitrum",
    listing_date_hint=datetime(2023, 3, 23, tzinfo=timezone.utc),
    manual_circulating_supply=1_275_000_000,
)

# Display results
formatter = TableFormatter()
print(formatter.format(result))

# Access specific data
print(f"Initial FDV: ${result.valuation.initial_fdv:,.0f}")
print(f"Total Raised: ${result.valuation.total_raised_usd:,.0f}")
```

## Data Sources

| Data Type | Primary Source | Secondary Source |
|-----------|----------------|------------------|
| Initial Listing Price | CCXT (multi-exchange) | CoinGecko Historical |
| Token Supply | CoinGecko | Manual Override |
| Categories | CoinGecko | - |
| Fundraising | CryptoRank | - |
| Allocations | CryptoRank | Manual YAML files |
| Vesting | CryptoRank | Manual Override |

## Canonical Allocation Buckets

Raw allocation labels are mapped to these canonical buckets:

| Bucket | Display Name | Example Labels |
|--------|--------------|----------------|
| `team_founder` | Team / Founder | Team, Founders, Core Team, Employees |
| `advisors_partner` | Advisors / Partners | Advisors, Partners, Consultants |
| `investors` | Investors | Seed, Private, Series A, Strategic |
| `public_sales` | Public Sales | ICO, IDO, IEO, Public Sale |
| `airdrop` | Airdrop | Airdrop, Retroactive, User Distribution |
| `community_rewards` | Community / Rewards | Rewards, Mining, Staking, Incentives |
| `listing_liquidity` | Listing / Liquidity | Liquidity, Market Making, Exchange |
| `ecosystem_rd` | Ecosystem / R&D | Ecosystem, Development, Growth |
| `treasury_reserve` | Treasury / Reserve | Treasury, Reserve, DAO Treasury |
| `unknown` | Unknown / Other | (fallback) |

Mapping rules are configurable in `config/allocation_mapping.yaml`.

## Output Formats

### Table (CLI)
Rich, colored tables for quick inspection in terminal.

### JSON
Complete machine-readable output with all fields:
```json
{
  "token": {...},
  "reference_price": {...},
  "valuation": {...},
  "allocations": {
    "raw_allocations": [...],
    "mapped_allocations": [...],
    "conflicts": [...]
  },
  "audit_trail": [...]
}
```

### CSV
Spreadsheet-compatible format with sections for:
- Token Information
- Initial Listing Data
- Valuation Metrics
- Supply Data
- Token Allocation Table
- Data Quality Flags

## Configuration

### API Keys (Optional)

Set environment variables for higher rate limits:
```bash
export COINGECKO_API_KEY=your_key_here
export CRYPTORANK_API_KEY=your_key_here
```

### Allocation Mapping

Customize mapping rules in `config/allocation_mapping.yaml`:
```yaml
canonical_buckets:
  team_founder:
    patterns:
      - "^team$"
      - "^founder"
    priority: 10
```

### Manual Overrides

Create YAML files in `data/manual/` for manual allocation data:
```yaml
# data/manual/arbitrum.yaml
allocations:
  - label: "Team"
    percentage: 15.0
    vesting:
      tge_unlock_pct: 0
      cliff_months: 12
      vesting_months: 36
      schedule_type: linear
```

## Key Design Decisions

### Circulating Supply at Listing
- **Problem**: Historical circulating supply is rarely available from aggregators
- **Solution**: Require manual override or clearly flag as estimated
- **Impact**: Initial Market Cap may be unavailable without manual input

### Price Selection
- **Default**: Earliest candle open price across all exchanges
- **Fallback**: CoinGecko daily data (lower confidence)
- **Alternative**: Manual override for known listing prices

### Allocation Conflicts
- When sources disagree, all values are preserved
- Conflicts are flagged with discrepancy percentage
- Analyst can review and select preferred source

## Formulas

```
Market Cap = circulating_supply × price
FDV = fully_diluted_supply × price
FDV/Raised Ratio = FDV / total_raised
```

## Testing

```bash
# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

## Project Structure

```
token_listing_tool/
├── config/                 # Configuration files
│   ├── settings.yaml
│   ├── exchanges.yaml
│   └── allocation_mapping.yaml
├── src/
│   ├── core/              # Data models and types
│   ├── resolution/        # Token identifier resolution
│   ├── providers/         # Data source providers
│   │   ├── price/        # CCXT, CoinGecko price
│   │   ├── supply/       # Supply data
│   │   ├── fundraising/  # CryptoRank fundraising
│   │   └── allocations/  # Allocation data
│   ├── allocation_mapper/ # Label mapping logic
│   ├── calculator/        # Valuation calculations
│   ├── output/           # Formatters
│   └── orchestrator.py   # Main pipeline
├── cli/                   # CLI interface
├── tests/                 # Test suite
└── examples/              # Example scripts
```

## Limitations

- **DEX-first tokens**: No on-chain integration for DEX listings (future enhancement)
- **Historical circulating supply**: Requires manual input for accurate initial market cap
- **Allocation data coverage**: Depends on CryptoRank data availability
- **Exchange historical data**: Limited by exchange data retention policies

## Future Enhancements

1. On-chain integration for DEX listings (Uniswap, etc.)
2. Vesting contract verification via on-chain queries
3. Automatic TGE circulating supply estimation from tokenomics
4. Peer benchmarking analysis within categories
5. Historical price charts and FDV evolution

## License

Internal tool - proprietary use only.
