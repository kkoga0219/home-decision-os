"""Tests for rental cashflow calculation."""

from app.domain.rental_cashflow import calc_rental_cashflow


class TestRentalCashflow:
    def test_positive_cashflow(self):
        result = calc_rental_cashflow(
            expected_rent=150_000,
            vacancy_rate=0.05,
            management_fee_rate=0.05,
            ownership_cost_monthly=100_000,
        )
        # vacancy: 7500, management: 7500, effective: 135000
        assert result.vacancy_loss == 7_500
        assert result.management_commission == 7_500
        assert result.effective_rent == 135_000
        assert result.monthly_cashflow == 35_000
        assert result.annual_cashflow == 35_000 * 12

    def test_negative_cashflow(self):
        result = calc_rental_cashflow(
            expected_rent=100_000,
            vacancy_rate=0.10,
            management_fee_rate=0.05,
            ownership_cost_monthly=120_000,
        )
        # vacancy: 10000, management: 5000, effective: 85000
        assert result.effective_rent == 85_000
        assert result.monthly_cashflow == -35_000

    def test_zero_rent(self):
        result = calc_rental_cashflow(
            expected_rent=0,
            vacancy_rate=0.05,
            management_fee_rate=0.05,
            ownership_cost_monthly=100_000,
        )
        assert result.monthly_cashflow == -100_000
