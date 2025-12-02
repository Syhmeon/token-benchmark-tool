"""Tests for allocation mapper module."""

import pytest

from src.allocation_mapper.mapper import AllocationMapper
from src.allocation_mapper.vesting_parser import VestingParser
from src.core.models import RawAllocation
from src.core.types import CanonicalBucket, DataSource, VestingScheduleType


class TestAllocationMapper:
    """Tests for AllocationMapper class."""

    def test_map_team_labels(self):
        """Test mapping of team-related labels."""
        mapper = AllocationMapper()

        test_cases = [
            ("Team", CanonicalBucket.TEAM_FOUNDER),
            ("Founders", CanonicalBucket.TEAM_FOUNDER),
            ("Core Team", CanonicalBucket.TEAM_FOUNDER),
            ("Development Team", CanonicalBucket.TEAM_FOUNDER),
            ("Employees", CanonicalBucket.TEAM_FOUNDER),
        ]

        for label, expected_bucket in test_cases:
            bucket, _, _ = mapper.map_label(label)
            assert bucket == expected_bucket, f"'{label}' should map to {expected_bucket}"

    def test_map_investor_labels(self):
        """Test mapping of investor-related labels."""
        mapper = AllocationMapper()

        test_cases = [
            ("Seed", CanonicalBucket.INVESTORS),
            ("Private Sale", CanonicalBucket.INVESTORS),
            ("Strategic Round", CanonicalBucket.INVESTORS),
            ("Series A", CanonicalBucket.INVESTORS),
            ("Investors", CanonicalBucket.INVESTORS),
            ("Early Investors", CanonicalBucket.INVESTORS),
        ]

        for label, expected_bucket in test_cases:
            bucket, _, _ = mapper.map_label(label)
            assert bucket == expected_bucket, f"'{label}' should map to {expected_bucket}"

    def test_map_public_sale_labels(self):
        """Test mapping of public sale labels."""
        mapper = AllocationMapper()

        test_cases = [
            ("Public Sale", CanonicalBucket.PUBLIC_SALES),
            ("ICO", CanonicalBucket.PUBLIC_SALES),
            ("IDO", CanonicalBucket.PUBLIC_SALES),
            ("Token Sale", CanonicalBucket.PUBLIC_SALES),
        ]

        for label, expected_bucket in test_cases:
            bucket, _, _ = mapper.map_label(label)
            assert bucket == expected_bucket, f"'{label}' should map to {expected_bucket}"

    def test_map_airdrop_labels(self):
        """Test mapping of airdrop labels."""
        mapper = AllocationMapper()

        test_cases = [
            ("Airdrop", CanonicalBucket.AIRDROP),
            ("Retroactive Airdrop", CanonicalBucket.AIRDROP),
            ("User Distribution", CanonicalBucket.AIRDROP),
        ]

        for label, expected_bucket in test_cases:
            bucket, _, _ = mapper.map_label(label)
            assert bucket == expected_bucket, f"'{label}' should map to {expected_bucket}"

    def test_map_treasury_labels(self):
        """Test mapping of treasury labels."""
        mapper = AllocationMapper()

        test_cases = [
            ("Treasury", CanonicalBucket.TREASURY_RESERVE),
            ("Reserve", CanonicalBucket.TREASURY_RESERVE),
            ("Strategic Reserve", CanonicalBucket.TREASURY_RESERVE),
            ("DAO Treasury", CanonicalBucket.TREASURY_RESERVE),
        ]

        for label, expected_bucket in test_cases:
            bucket, _, _ = mapper.map_label(label)
            assert bucket == expected_bucket, f"'{label}' should map to {expected_bucket}"

    def test_map_unknown_label(self):
        """Test that unknown labels map to UNKNOWN bucket."""
        mapper = AllocationMapper()
        bucket, _, _ = mapper.map_label("Random Gibberish XYZ123")
        assert bucket == CanonicalBucket.UNKNOWN

    def test_map_allocations_aggregation(self, sample_raw_allocations):
        """Test that allocations are properly aggregated."""
        mapper = AllocationMapper()
        result = mapper.map_allocations(sample_raw_allocations)

        assert len(result.mapped_allocations) > 0
        assert result.total_percentage is not None
        assert len(result.sources_used) > 0

    def test_map_allocations_preserves_raw(self, sample_raw_allocations):
        """Test that raw allocations are preserved."""
        mapper = AllocationMapper()
        result = mapper.map_allocations(sample_raw_allocations)

        assert len(result.raw_allocations) == len(sample_raw_allocations)


class TestVestingParser:
    """Tests for VestingParser class."""

    def test_parse_tge_unlock(self):
        """Test parsing TGE unlock percentages."""
        parser = VestingParser()

        test_cases = [
            ("10% TGE", 10.0),
            ("10% at TGE", 10.0),
            ("10% at launch", 10.0),
            ("TGE unlock of 20%", 20.0),
            ("15.5% initial unlock", 15.5),
        ]

        for text, expected_tge in test_cases:
            result = parser.parse(text)
            assert result is not None
            assert result.tge_unlock_pct == expected_tge, f"'{text}' should have {expected_tge}% TGE"

    def test_parse_cliff(self):
        """Test parsing cliff periods."""
        parser = VestingParser()

        test_cases = [
            ("6 month cliff", 6),
            ("6-month cliff", 6),
            ("cliff of 12 months", 12),
            ("1 year cliff", 12),  # Should convert years to months
        ]

        for text, expected_cliff in test_cases:
            result = parser.parse(text)
            assert result is not None
            assert result.cliff_months == expected_cliff, f"'{text}' should have {expected_cliff} month cliff"

    def test_parse_vesting_duration(self):
        """Test parsing vesting duration."""
        parser = VestingParser()

        test_cases = [
            ("24 months linear", 24),
            ("linear over 36 months", 36),
            ("2 years vesting", 24),
        ]

        for text, expected_months in test_cases:
            result = parser.parse(text)
            assert result is not None
            assert result.vesting_months == expected_months, f"'{text}' should have {expected_months} months"

    def test_parse_schedule_type(self):
        """Test parsing schedule types."""
        parser = VestingParser()

        linear_result = parser.parse("24 months linear vesting")
        assert linear_result.schedule_type == VestingScheduleType.LINEAR

        monthly_result = parser.parse("monthly unlocks over 12 months")
        assert monthly_result.schedule_type == VestingScheduleType.STEP

    def test_parse_complex_vesting(self):
        """Test parsing complex vesting strings."""
        parser = VestingParser()

        text = "10% TGE, 6 month cliff, 24 months linear"
        result = parser.parse(text)

        assert result is not None
        assert result.tge_unlock_pct == 10.0
        assert result.cliff_months == 6
        assert result.vesting_months == 24
        assert result.schedule_type == VestingScheduleType.LINEAR

    def test_format_summary(self):
        """Test formatting vesting summary."""
        from src.core.models import VestingTerms

        parser = VestingParser()

        terms = VestingTerms(
            tge_unlock_pct=10.0,
            cliff_months=6,
            vesting_months=24,
            schedule_type=VestingScheduleType.LINEAR,
        )

        summary = parser.format_summary(terms)
        assert "10%" in summary
        assert "6mo cliff" in summary
        assert "24mo" in summary
