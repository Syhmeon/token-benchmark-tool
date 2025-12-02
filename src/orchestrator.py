"""Main orchestrator for the token listing analysis pipeline.

Coordinates all providers and processors to produce a complete
TokenListingResult from a token identifier.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from .core.models import (
    AuditEntry,
    DataQualityFlag,
    TokenInfo,
    TokenListingResult,
)
from .core.types import ConfidenceLevel, DataSource, PriceSelectionMethod
from .resolution.token_resolver import TokenResolver
from .providers.price.ccxt_provider import CCXTPriceProvider
from .providers.price.coingecko_price import CoinGeckoPriceProvider
from .providers.supply.coingecko_supply import CoinGeckoSupplyProvider
from .providers.fundraising.cryptorank import CryptoRankFundraisingProvider
from .providers.allocations.cryptorank_alloc import CryptoRankAllocationProvider
from .providers.allocations.manual_alloc import ManualAllocationProvider
from .allocation_mapper.mapper import AllocationMapper
from .allocation_mapper.conflict_detector import ConflictDetector
from .calculator.valuation import ValuationCalculator
from .calculator.price_selector import PriceSelector

logger = logging.getLogger(__name__)


class TokenListingOrchestrator:
    """Orchestrates the complete token listing analysis pipeline."""

    def __init__(
        self,
        coingecko_api_key: str | None = None,
        cryptorank_api_key: str | None = None,
        exchanges: list[str] | None = None,
        allocation_config_path: Path | str | None = None,
        manual_data_directory: Path | str | None = None,
    ):
        """
        Initialize the orchestrator with all providers.

        Args:
            coingecko_api_key: CoinGecko API key (uses env var COINGECKO_API_KEY if not provided)
            cryptorank_api_key: CryptoRank API key (uses env var CRYPTORANK_API_KEY if not provided)
            exchanges: List of exchange IDs to check (default: major exchanges)
            allocation_config_path: Path to allocation mapping YAML config
            manual_data_directory: Directory for manual override files
        """
        # Get API keys from environment if not provided
        self.coingecko_api_key = coingecko_api_key or os.environ.get("COINGECKO_API_KEY")
        self.cryptorank_api_key = cryptorank_api_key or os.environ.get("CRYPTORANK_API_KEY")

        # Initialize providers
        self.token_resolver = TokenResolver(api_key=self.coingecko_api_key)

        self.ccxt_provider = CCXTPriceProvider(exchanges=exchanges)
        self.coingecko_price = CoinGeckoPriceProvider(api_key=self.coingecko_api_key)
        self.supply_provider = CoinGeckoSupplyProvider(api_key=self.coingecko_api_key)
        self.fundraising_provider = CryptoRankFundraisingProvider(api_key=self.cryptorank_api_key)
        self.allocation_provider = CryptoRankAllocationProvider(api_key=self.cryptorank_api_key)
        self.manual_allocation_provider = ManualAllocationProvider(data_directory=manual_data_directory)

        # Initialize processors
        self.allocation_mapper = AllocationMapper(config_path=allocation_config_path)
        self.conflict_detector = ConflictDetector()
        self.price_selector = PriceSelector()
        self.valuation_calculator = ValuationCalculator()

        # Audit trail
        self._audit_entries: list[AuditEntry] = []
        self._quality_flags: list[DataQualityFlag] = []

    def _add_audit(
        self,
        source: DataSource,
        action: str,
        endpoint: str | None = None,
        success: bool = True,
        error_message: str | None = None,
        notes: str | None = None,
    ) -> None:
        """Add an audit entry."""
        self._audit_entries.append(
            AuditEntry(
                source=source,
                action=action,
                endpoint=endpoint,
                success=success,
                error_message=error_message,
                notes=notes,
            )
        )

    def _add_quality_flag(
        self,
        field: str,
        issue: str,
        severity: str = "warning",
    ) -> None:
        """Add a data quality flag."""
        self._quality_flags.append(
            DataQualityFlag(field=field, issue=issue, severity=severity)
        )

    def _collect_provider_audits(self) -> None:
        """Collect audit entries from all providers."""
        providers = [
            self.ccxt_provider,
            self.coingecko_price,
            self.supply_provider,
            self.fundraising_provider,
            self.allocation_provider,
        ]

        for provider in providers:
            self._audit_entries.extend(provider.get_audit_trail())
            provider.clear_audit_trail()

    def analyze(
        self,
        token_identifier: str,
        listing_date_hint: datetime | None = None,
        manual_circulating_supply: float | None = None,
        manual_initial_price: float | None = None,
        price_selection_method: PriceSelectionMethod = PriceSelectionMethod.EARLIEST_OPEN,
    ) -> TokenListingResult:
        """
        Perform complete token listing analysis.

        Args:
            token_identifier: Token symbol, CoinGecko ID, or contract address
            listing_date_hint: Optional hint for when token was listed
            manual_circulating_supply: Manual override for circulating supply at listing
            manual_initial_price: Manual override for initial price
            price_selection_method: Method to select reference price

        Returns:
            TokenListingResult with all available data
        """
        logger.info(f"Starting analysis for: {token_identifier}")

        # Reset audit trail
        self._audit_entries = []
        self._quality_flags = []

        # Step 1: Resolve token
        logger.info("Step 1: Resolving token identifier...")
        try:
            token_info = self.token_resolver.resolve(token_identifier)
            self._add_audit(
                DataSource.COINGECKO,
                "resolve",
                endpoint=f"/coins/{token_info.coingecko_id}",
                success=True,
                notes=f"Resolved to {token_info.symbol}",
            )
        except Exception as e:
            logger.error(f"Failed to resolve token: {e}")
            self._add_audit(
                DataSource.COINGECKO,
                "resolve",
                success=False,
                error_message=str(e),
            )
            raise

        # Step 2: Get listing prices from exchanges
        logger.info("Step 2: Fetching exchange listing data...")
        exchange_listings = self.ccxt_provider.get_listings_all_exchanges(
            symbol=token_info.symbol,
            since_hint=listing_date_hint or token_info.genesis_date,
        )

        # Get CoinGecko price as fallback
        coingecko_listing = self.coingecko_price.get_listing_data(
            token_info.coingecko_id,
            listing_date_hint=listing_date_hint,
        )

        # Step 3: Select reference price
        logger.info("Step 3: Selecting reference initial price...")
        if manual_initial_price:
            reference_price = self.price_selector.create_manual_price(
                price_usd=manual_initial_price,
                timestamp=listing_date_hint,
                notes="Manually specified by analyst",
            )
        else:
            reference_price = self.price_selector.select_with_fallback(
                exchange_listings=exchange_listings,
                coingecko_listing=coingecko_listing,
                method=price_selection_method,
            )

        if not reference_price:
            self._add_quality_flag(
                "reference_price",
                "Could not determine initial listing price from any source",
                severity="error",
            )

        # Step 4: Get supply data
        logger.info("Step 4: Fetching supply data...")
        supply_data = self.supply_provider.get_supply(
            token_info.coingecko_id,
            manual_circulating_at_listing=manual_circulating_supply,
        )

        if not supply_data.circulating_supply_at_listing:
            self._add_quality_flag(
                "circulating_supply",
                "Circulating supply at listing is unknown. Initial Market Cap cannot be calculated accurately.",
                severity="warning",
            )

        # Step 5: Get fundraising data
        logger.info("Step 5: Fetching fundraising data...")
        fundraising_data = None
        try:
            fundraising_data = self.fundraising_provider.get_fundraising_by_coingecko_id(
                token_info.coingecko_id
            )
            if not fundraising_data or not fundraising_data.total_raised_usd:
                self._add_quality_flag(
                    "fundraising",
                    "No fundraising data available. FDV/Raised ratio cannot be calculated.",
                    severity="info",
                )
        except Exception as e:
            logger.warning(f"Failed to fetch fundraising data: {e}")
            self._add_audit(
                DataSource.CRYPTORANK,
                "fetch_fundraising",
                success=False,
                error_message=str(e),
            )

        # Step 6: Get allocation data
        logger.info("Step 6: Fetching allocation data...")
        raw_allocations = []

        # Try CryptoRank
        try:
            cryptorank_allocations = self.allocation_provider.get_allocations_by_coingecko_id(
                token_info.coingecko_id
            )
            raw_allocations.extend(cryptorank_allocations)
        except Exception as e:
            logger.warning(f"Failed to fetch allocations from CryptoRank: {e}")

        # Try manual overrides
        if self.manual_allocation_provider.is_available():
            manual_allocations = self.manual_allocation_provider.get_allocations(
                token_info.coingecko_id
            )
            raw_allocations.extend(manual_allocations)

        # Step 7: Map allocations
        logger.info("Step 7: Mapping allocations to canonical buckets...")
        allocation_data = None
        if raw_allocations:
            allocation_data = self.allocation_mapper.map_allocations(raw_allocations)

            # Detect conflicts
            conflicts = self.conflict_detector.detect_conflicts(allocation_data)
            if conflicts:
                # Add conflicts to allocation data
                allocation_data = allocation_data.model_copy(update={"conflicts": conflicts})

                for conflict in conflicts:
                    self._add_quality_flag(
                        f"allocation:{conflict.canonical_bucket.value}",
                        f"Conflict between sources: {conflict.discrepancy_pct:.1f}% discrepancy",
                        severity="warning",
                    )

            # Check totals
            total_issues = self.conflict_detector.detect_total_issues(allocation_data)
            for issue in total_issues:
                self._add_quality_flag("allocation_total", issue, severity="warning")
        else:
            self._add_quality_flag(
                "allocations",
                "No allocation data available from any source",
                severity="info",
            )

        # Step 8: Calculate valuation metrics
        logger.info("Step 8: Calculating valuation metrics...")
        valuation = None
        if reference_price:
            valuation = self.valuation_calculator.calculate(
                reference_price=reference_price,
                supply_data=supply_data,
                fundraising_data=fundraising_data,
            )

        # Step 9: Get peer tokens
        logger.info("Step 9: Identifying peer tokens...")
        peer_tokens = self._find_peers(token_info)

        # Collect all audit entries
        self._collect_provider_audits()

        # Build result
        result = TokenListingResult(
            token=token_info,
            exchange_listings=exchange_listings,
            reference_price=reference_price,
            supply=supply_data,
            valuation=valuation,
            fundraising=fundraising_data,
            allocations=allocation_data,
            peer_tokens=peer_tokens,
            audit_trail=self._audit_entries,
            quality_flags=self._quality_flags,
        )

        logger.info(f"Analysis complete for {token_info.symbol}")
        return result

    def _find_peers(self, token_info: TokenInfo) -> list[str]:
        """Find peer tokens in the same category."""
        # For MVP, just return category info
        # Future: query CoinGecko for tokens in same category
        peers = []

        if token_info.categories:
            # Just note the categories for now
            logger.info(f"Token categories: {token_info.categories}")

        return peers

    def analyze_batch(
        self,
        token_identifiers: list[str],
        **kwargs: Any,
    ) -> list[TokenListingResult]:
        """
        Analyze multiple tokens.

        Args:
            token_identifiers: List of token identifiers
            **kwargs: Passed to analyze()

        Returns:
            List of TokenListingResult objects
        """
        results = []
        for identifier in token_identifiers:
            try:
                result = self.analyze(identifier, **kwargs)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to analyze {identifier}: {e}")
                # Continue with other tokens

        return results
