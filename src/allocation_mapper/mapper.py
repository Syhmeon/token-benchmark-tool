"""Allocation mapper - maps raw labels to canonical buckets.

This module implements the core mapping logic that transforms
raw allocation labels from various sources into a standardized
set of canonical buckets.
"""

import logging
import re
from pathlib import Path
from typing import Any

import yaml

from ..core.models import (
    AllocationData,
    MappedAllocation,
    RawAllocation,
)
from ..core.types import CanonicalBucket, ConfidenceLevel, DataSource

logger = logging.getLogger(__name__)


# Default mapping rules (used if no config file provided)
DEFAULT_MAPPING_RULES: dict[str, dict[str, Any]] = {
    "team_founder": {
        "patterns": [
            r"^team$",
            r"^founder",
            r"^core.*team",
            r"^development.*team",
            r"^founding",
            r"^employee",
            r"^staff",
            r"^core.*contributor",
        ],
        "priority": 10,
    },
    "advisors_partner": {
        "patterns": [
            r"^advisor",
            r"^partner",
            r"^strategic.*partner",
            r"^consultant",
        ],
        "priority": 10,
    },
    "investors": {
        "patterns": [
            r"^investor",
            r"^seed",
            r"^private",
            r"^strategic.*sale",
            r"^strategic.*round",
            r"^series.*[a-z]",
            r"^vc",
            r"^venture",
            r"^early.*investor",
            r"^pre.*seed",
            r"^angel",
            r"^launchpad",
        ],
        "priority": 10,
    },
    "public_sales": {
        "patterns": [
            r"^public",
            r"^ico$",
            r"^ido$",
            r"^ieo$",
            r"^token.*sale",
            r"^crowd.*sale",
            r"^community.*sale",
        ],
        "priority": 10,
    },
    "airdrop": {
        "patterns": [
            r"^airdrop",
            r"^air.*drop",
            r"^retro.*drop",
            r"^retroactive",
            r"^user.*distribution",
            r"^user.*allocation",
        ],
        "priority": 10,
    },
    "community_rewards": {
        "patterns": [
            r"^community(?!.*sale)",
            r"^reward",
            r"^incentive",
            r"^mining",
            r"^staking.*reward",
            r"^yield",
            r"^emission",
            r"^farming",
            r"^liquidity.*mining",
            r"^governance.*reward",
            r"^contributor(?!.*core)",
            r"^grant",
            r"^bounty",
        ],
        "priority": 9,
    },
    "listing_liquidity": {
        "patterns": [
            r"^listing",
            r"^liquidity(?!.*mining)",
            r"^market.*mak",
            r"^exchange",
            r"^cex",
            r"^dex.*liquidity",
            r"^trading",
        ],
        "priority": 10,
    },
    "ecosystem_rd": {
        "patterns": [
            r"^ecosystem",
            r"^development(?!.*team)",
            r"^r&d",
            r"^research",
            r"^protocol.*development",
            r"^network.*development",
            r"^growth",
            r"^adoption",
            r"^integration",
            r"^foundation",
            r"^dao(?!.*treasury)",
        ],
        "priority": 8,
    },
    "treasury_reserve": {
        "patterns": [
            r"^treasury",
            r"^reserve",
            r"^strategic.*reserve",
            r"^emergency",
            r"^insurance",
            r"^protocol.*owned",
            r"^dao.*treasury",
        ],
        "priority": 10,
    },
}


class AllocationMapper:
    """Maps raw allocation labels to canonical buckets."""

    def __init__(self, config_path: Path | str | None = None):
        """
        Initialize allocation mapper.

        Args:
            config_path: Path to YAML configuration file with mapping rules.
                If None, uses default rules.
        """
        self.rules: dict[str, dict[str, Any]] = {}
        self.source_overrides: dict[str, dict[str, str]] = {}
        self._compiled_patterns: dict[str, list[tuple[re.Pattern, int]]] = {}

        if config_path:
            self._load_config(Path(config_path))
        else:
            self.rules = DEFAULT_MAPPING_RULES

        self._compile_patterns()

    def _load_config(self, config_path: Path) -> None:
        """Load mapping rules from YAML config."""
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            if "canonical_buckets" in config:
                self.rules = config["canonical_buckets"]
            else:
                self.rules = DEFAULT_MAPPING_RULES
                logger.warning(
                    f"No 'canonical_buckets' in {config_path}, using defaults"
                )

            self.source_overrides = config.get("source_overrides", {})

            logger.info(f"Loaded mapping config from {config_path}")

        except FileNotFoundError:
            logger.warning(f"Config file not found: {config_path}, using defaults")
            self.rules = DEFAULT_MAPPING_RULES
        except yaml.YAMLError as e:
            logger.error(f"Invalid YAML in {config_path}: {e}")
            self.rules = DEFAULT_MAPPING_RULES

    def _compile_patterns(self) -> None:
        """Pre-compile regex patterns for efficiency."""
        self._compiled_patterns = {}

        for bucket, config in self.rules.items():
            patterns = config.get("patterns", [])
            priority = config.get("priority", 5)

            compiled = []
            for pattern in patterns:
                try:
                    compiled.append((re.compile(pattern, re.IGNORECASE), priority))
                except re.error as e:
                    logger.error(f"Invalid regex pattern '{pattern}': {e}")

            self._compiled_patterns[bucket] = compiled

    def _check_source_override(
        self,
        source: DataSource,
        label: str,
    ) -> str | None:
        """Check if there's a source-specific override for this label."""
        source_key = source.value
        overrides = self.source_overrides.get(source_key, {})
        return overrides.get(label)

    def map_label(
        self,
        label: str,
        source: DataSource = DataSource.UNKNOWN,
    ) -> tuple[CanonicalBucket, str, int]:
        """
        Map a single label to a canonical bucket.

        Args:
            label: Raw allocation label
            source: Data source (for source-specific overrides)

        Returns:
            Tuple of (canonical_bucket, matched_rule, priority)
        """
        label_clean = label.strip()

        # Check source-specific override first
        override = self._check_source_override(source, label_clean)
        if override:
            try:
                bucket = CanonicalBucket(override)
                return bucket, f"source_override:{source.value}", 100
            except ValueError:
                logger.warning(f"Invalid override bucket '{override}' for '{label}'")

        # Try pattern matching
        best_match: tuple[CanonicalBucket, str, int] | None = None

        for bucket_name, patterns in self._compiled_patterns.items():
            for pattern, priority in patterns:
                if pattern.search(label_clean):
                    try:
                        bucket = CanonicalBucket(bucket_name)
                    except ValueError:
                        continue

                    if best_match is None or priority > best_match[2]:
                        best_match = (bucket, pattern.pattern, priority)

        if best_match:
            return best_match

        # No match found - return unknown
        return CanonicalBucket.UNKNOWN, "no_match", 0

    def map_allocations(
        self,
        raw_allocations: list[RawAllocation],
    ) -> AllocationData:
        """
        Map a list of raw allocations to canonical buckets.

        This method:
        1. Maps each raw allocation to a canonical bucket
        2. Aggregates allocations that map to the same bucket
        3. Tracks original labels and sources
        4. Calculates total percentage

        Args:
            raw_allocations: List of RawAllocation objects

        Returns:
            AllocationData with mapped allocations
        """
        if not raw_allocations:
            return AllocationData()

        # Group by canonical bucket
        bucket_groups: dict[CanonicalBucket, list[tuple[RawAllocation, str]]] = {}

        for raw in raw_allocations:
            bucket, rule, _ = self.map_label(raw.label, raw.source)

            if bucket not in bucket_groups:
                bucket_groups[bucket] = []
            bucket_groups[bucket].append((raw, rule))

        # Create mapped allocations
        mapped = []
        total_percentage = 0.0

        for bucket, items in bucket_groups.items():
            # Aggregate data from all raw allocations in this bucket
            original_labels = []
            sources = set()
            total_pct = 0.0
            total_amount = 0.0
            has_pct = False
            has_amount = False
            vesting = None
            mapping_rules = set()

            for raw, rule in items:
                original_labels.append(raw.label)
                sources.add(raw.source)
                mapping_rules.add(rule)

                if raw.percentage is not None:
                    total_pct += raw.percentage
                    has_pct = True
                if raw.amount is not None:
                    total_amount += raw.amount
                    has_amount = True

                # Use first vesting info available
                if vesting is None and raw.vesting:
                    vesting = raw.vesting

            # Determine confidence based on sources
            if DataSource.MANUAL in sources:
                confidence = ConfidenceLevel.HIGH
            elif len(sources) > 1:
                confidence = ConfidenceLevel.MEDIUM
            else:
                confidence = ConfidenceLevel.MEDIUM

            mapped_alloc = MappedAllocation(
                canonical_bucket=bucket,
                display_name=bucket.display_name,
                original_labels=list(set(original_labels)),
                percentage=total_pct if has_pct else None,
                amount=total_amount if has_amount else None,
                sources=list(sources),
                vesting=vesting,
                confidence=confidence,
                mapping_rule=" | ".join(mapping_rules),
            )
            mapped.append(mapped_alloc)

            if has_pct:
                total_percentage += total_pct

        # Sort by canonical bucket order
        bucket_order = list(CanonicalBucket)
        mapped.sort(key=lambda x: bucket_order.index(x.canonical_bucket))

        # Determine if allocations are complete (sum to ~100%)
        is_complete = 95.0 <= total_percentage <= 105.0

        # Collect all sources used
        all_sources = list(set(raw.source for raw in raw_allocations))

        return AllocationData(
            raw_allocations=raw_allocations,
            mapped_allocations=mapped,
            total_percentage=total_percentage if total_percentage > 0 else None,
            is_complete=is_complete,
            sources_used=all_sources,
        )

    def get_bucket_for_label(self, label: str) -> CanonicalBucket:
        """
        Simple helper to get just the bucket for a label.

        Args:
            label: Raw allocation label

        Returns:
            CanonicalBucket
        """
        bucket, _, _ = self.map_label(label)
        return bucket
