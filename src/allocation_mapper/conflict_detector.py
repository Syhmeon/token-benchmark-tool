"""Conflict detection for allocation data from multiple sources.

When multiple sources provide allocation data, they may disagree.
This module detects and records such conflicts for analyst review.
"""

import logging
from collections import defaultdict

from ..core.models import (
    AllocationConflict,
    AllocationData,
    RawAllocation,
)
from ..core.types import CanonicalBucket, DataSource

logger = logging.getLogger(__name__)


class ConflictDetector:
    """Detects conflicts between allocation data from different sources."""

    def __init__(
        self,
        percentage_threshold: float = 5.0,
        total_allocation_min: float = 95.0,
        total_allocation_max: float = 105.0,
    ):
        """
        Initialize conflict detector.

        Args:
            percentage_threshold: Flag as conflict if values differ by more than this
            total_allocation_min: Flag if total is below this percentage
            total_allocation_max: Flag if total is above this percentage
        """
        self.percentage_threshold = percentage_threshold
        self.total_allocation_min = total_allocation_min
        self.total_allocation_max = total_allocation_max

    def detect_conflicts(
        self,
        allocation_data: AllocationData,
        bucket_map: dict[str, CanonicalBucket] | None = None,
    ) -> list[AllocationConflict]:
        """
        Detect conflicts in allocation data.

        Args:
            allocation_data: AllocationData with raw allocations from multiple sources
            bucket_map: Optional pre-computed label -> bucket mapping

        Returns:
            List of AllocationConflict objects
        """
        conflicts = []

        # Group raw allocations by source and bucket
        source_bucket_values: dict[
            CanonicalBucket, dict[DataSource, list[float]]
        ] = defaultdict(lambda: defaultdict(list))

        for raw in allocation_data.raw_allocations:
            if raw.percentage is None:
                continue

            # Find the bucket this raw allocation maps to
            if bucket_map:
                bucket = bucket_map.get(raw.label, CanonicalBucket.UNKNOWN)
            else:
                # Find from mapped allocations
                bucket = CanonicalBucket.UNKNOWN
                for mapped in allocation_data.mapped_allocations:
                    if raw.label in mapped.original_labels:
                        bucket = mapped.canonical_bucket
                        break

            source_bucket_values[bucket][raw.source].append(raw.percentage)

        # Check for conflicts between sources for same bucket
        for bucket, source_values in source_bucket_values.items():
            if len(source_values) < 2:
                continue  # Need at least 2 sources to have conflict

            # Calculate average per source
            source_averages: dict[DataSource, float] = {}
            for source, values in source_values.items():
                source_averages[source] = sum(values)  # Sum if multiple allocations map to same bucket

            # Find maximum discrepancy
            sources = list(source_averages.keys())
            values = list(source_averages.values())

            max_val = max(values)
            min_val = min(values)
            discrepancy = max_val - min_val

            if discrepancy > self.percentage_threshold:
                # Create conflict record
                values_dict = {s.value: v for s, v in source_averages.items()}

                conflict = AllocationConflict(
                    canonical_bucket=bucket,
                    sources_involved=sources,
                    values=values_dict,
                    discrepancy_pct=discrepancy,
                    resolution=None,
                    preferred_source=None,
                )
                conflicts.append(conflict)

                logger.warning(
                    f"Allocation conflict for {bucket.value}: "
                    f"discrepancy={discrepancy:.1f}% between {[s.value for s in sources]}"
                )

        return conflicts

    def detect_total_issues(
        self,
        allocation_data: AllocationData,
    ) -> list[str]:
        """
        Check if total allocations are within acceptable range.

        Args:
            allocation_data: AllocationData with mapped allocations

        Returns:
            List of warning messages
        """
        issues = []

        # Check per-source totals
        source_totals: dict[DataSource, float] = defaultdict(float)

        for raw in allocation_data.raw_allocations:
            if raw.percentage is not None:
                source_totals[raw.source] += raw.percentage

        for source, total in source_totals.items():
            if total < self.total_allocation_min:
                issues.append(
                    f"[{source.value}] Total allocation ({total:.1f}%) is below "
                    f"expected minimum ({self.total_allocation_min}%). "
                    f"Some allocations may be missing."
                )
            elif total > self.total_allocation_max:
                issues.append(
                    f"[{source.value}] Total allocation ({total:.1f}%) exceeds "
                    f"expected maximum ({self.total_allocation_max}%). "
                    f"Some allocations may be duplicated or incorrect."
                )

        return issues

    def suggest_resolution(
        self,
        conflict: AllocationConflict,
        preferred_sources: list[DataSource] | None = None,
    ) -> AllocationConflict:
        """
        Suggest a resolution for a conflict.

        Args:
            conflict: The conflict to resolve
            preferred_sources: Ordered list of preferred sources

        Returns:
            Updated conflict with resolution suggestion
        """
        preferred_sources = preferred_sources or [
            DataSource.MANUAL,
            DataSource.CRYPTORANK,
            DataSource.COINGECKO,
        ]

        # Find the best source among those involved
        best_source = None
        for source in preferred_sources:
            if source in conflict.sources_involved:
                best_source = source
                break

        if best_source is None:
            # Use the source with the most reasonable value (closest to average)
            values = list(conflict.values.values())
            avg = sum(values) / len(values)

            min_diff = float("inf")
            for source in conflict.sources_involved:
                source_val = conflict.values.get(source.value, 0)
                diff = abs(source_val - avg)
                if diff < min_diff:
                    min_diff = diff
                    best_source = source

        resolution = (
            f"Suggested: use {best_source.value} value "
            f"({conflict.values.get(best_source.value, 'N/A')}%)"
        )

        return AllocationConflict(
            canonical_bucket=conflict.canonical_bucket,
            sources_involved=conflict.sources_involved,
            values=conflict.values,
            discrepancy_pct=conflict.discrepancy_pct,
            resolution=resolution,
            preferred_source=best_source,
        )
