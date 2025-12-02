"""Tests for valuation calculator module."""

import pytest
from datetime import datetime, timezone

from src.calculator.valuation import (
    ValuationCalculator,
    calc_fdv,
    calc_market_cap,
    calc_fdv_to_raised,
)
from src.core.models import (
    FundraisingData,
    FundraisingRound,
    ReferencePrice,
    SupplyData,
)
from src.core.types import ConfidenceLevel, DataSource, PriceSelectionMethod


class TestValuationFormulas:
    """Tests for standalone valuation formulas."""

    def test_calc_fdv(self):
        """Test FDV calculation."""
        # FDV = total_supply × price
        assert calc_fdv(1_000_000_000, 1.0) == 1_000_000_000
        assert calc_fdv(10_000_000_000, 1.25) == 12_500_000_000
        assert calc_fdv(100_000, 0.001) == 100

    def test_calc_market_cap(self):
        """Test market cap calculation."""
        # MCap = circulating × price
        assert calc_market_cap(500_000_000, 2.0) == 1_000_000_000
        assert calc_market_cap(1_275_000_000, 1.25) == 1_593_750_000

    def test_calc_fdv_to_raised(self):
        """Test FDV/Raised ratio calculation."""
        # 10B FDV / 100M raised = 100x
        assert calc_fdv_to_raised(10_000_000_000, 100_000_000) == 100.0
        # 1B FDV / 50M raised = 20x
        assert calc_fdv_to_raised(1_000_000_000, 50_000_000) == 20.0

    def test_calc_fdv_to_raised_zero_raised(self):
        """Test that zero raised raises error."""
        with pytest.raises(ValueError):
            calc_fdv_to_raised(1_000_000_000, 0)


class TestValuationCalculator:
    """Tests for ValuationCalculator class."""

    @pytest.fixture
    def reference_price(self):
        """Sample reference price."""
        return ReferencePrice(
            price_usd=1.25,
            timestamp=datetime(2023, 3, 23, 10, 0, 0, tzinfo=timezone.utc),
            method=PriceSelectionMethod.EARLIEST_OPEN,
            source_exchange="binance",
            source_pair="ARB/USDT",
            confidence=ConfidenceLevel.HIGH,
        )

    @pytest.fixture
    def supply_data(self):
        """Sample supply data."""
        return SupplyData(
            total_supply=10_000_000_000,
            max_supply=10_000_000_000,
            circulating_supply_current=3_475_000_000,
            circulating_supply_at_listing=1_275_000_000,
            circulating_supply_source=DataSource.MANUAL,
            circulating_supply_is_estimate=False,
        )

    @pytest.fixture
    def fundraising_data(self):
        """Sample fundraising data."""
        return FundraisingData(
            total_raised_usd=140_000_000,
            rounds=[
                FundraisingRound(
                    round_name="Series B",
                    amount_usd=120_000_000,
                ),
                FundraisingRound(
                    round_name="Series A",
                    amount_usd=20_000_000,
                ),
            ],
        )

    def test_calculate_all_metrics(self, reference_price, supply_data, fundraising_data):
        """Test full valuation calculation."""
        calculator = ValuationCalculator()
        result = calculator.calculate(reference_price, supply_data, fundraising_data)

        # Check FDV
        expected_fdv = 10_000_000_000 * 1.25  # 12.5B
        assert result.initial_fdv == expected_fdv
        assert result.fdv_confidence == ConfidenceLevel.HIGH

        # Check Market Cap
        expected_mcap = 1_275_000_000 * 1.25  # ~1.59B
        assert result.initial_market_cap == expected_mcap
        assert result.market_cap_confidence == ConfidenceLevel.HIGH

        # Check FDV/Raised
        expected_ratio = expected_fdv / 140_000_000  # ~89x
        assert abs(result.fdv_to_raised_ratio - expected_ratio) < 0.1

    def test_calculate_without_circulating(self, reference_price, fundraising_data):
        """Test calculation when circulating supply is unknown."""
        supply_data = SupplyData(
            total_supply=10_000_000_000,
            circulating_supply_at_listing=None,  # Unknown
            circulating_supply_is_estimate=True,
        )

        calculator = ValuationCalculator()
        result = calculator.calculate(reference_price, supply_data, fundraising_data)

        # FDV should still be calculated
        assert result.initial_fdv is not None

        # Market cap should be None (no circulating supply)
        assert result.initial_market_cap is None
        assert result.market_cap_confidence == ConfidenceLevel.UNKNOWN

    def test_calculate_without_fundraising(self, reference_price, supply_data):
        """Test calculation without fundraising data."""
        calculator = ValuationCalculator()
        result = calculator.calculate(reference_price, supply_data, None)

        # FDV and MCap should be calculated
        assert result.initial_fdv is not None
        assert result.initial_market_cap is not None

        # Ratio should be None
        assert result.fdv_to_raised_ratio is None
        assert result.total_raised_usd is None

    def test_calculation_notes(self, reference_price, supply_data, fundraising_data):
        """Test that calculation notes are generated."""
        calculator = ValuationCalculator()
        result = calculator.calculate(reference_price, supply_data, fundraising_data)

        assert len(result.calculation_notes) > 0
        # Should contain formulas
        assert any("FDV" in note for note in result.calculation_notes)
        assert any("Market Cap" in note for note in result.calculation_notes)
