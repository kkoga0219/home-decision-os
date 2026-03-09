"""Tests for mortgage calculation logic."""

from app.domain.mortgage import (
    approximate_outstanding_balance,
    calc_monthly_payment,
    calc_mortgage,
    calc_tax_credit_annual,
)


class TestCalcMonthlyPayment:
    def test_typical_loan(self):
        # 30M JPY, 0.5% annual rate, 35 years
        monthly = calc_monthly_payment(30_000_000, 0.005, 35)
        assert 77_000 <= monthly <= 78_000  # ~77,875

    def test_zero_interest(self):
        monthly = calc_monthly_payment(30_000_000, 0.0, 35)
        expected = 30_000_000 / (35 * 12)
        assert abs(monthly - expected) <= 1

    def test_zero_principal(self):
        assert calc_monthly_payment(0, 0.01, 35) == 0

    def test_high_interest(self):
        # 30M JPY, 3% annual rate, 35 years
        monthly = calc_monthly_payment(30_000_000, 0.03, 35)
        assert 115_000 <= monthly <= 116_000

    def test_short_term(self):
        # 10M JPY, 1%, 10 years
        monthly = calc_monthly_payment(10_000_000, 0.01, 10)
        assert 87_000 <= monthly <= 88_000


class TestCalcMortgage:
    def test_with_down_payment(self):
        result = calc_mortgage(
            price=40_000_000,
            down_payment=8_000_000,
            annual_rate=0.005,
            years=35,
        )
        assert result.loan_amount == 32_000_000
        assert result.monthly_payment > 0
        assert result.total_payment > result.loan_amount
        assert result.total_interest == result.total_payment - result.loan_amount

    def test_full_loan(self):
        result = calc_mortgage(price=30_000_000, down_payment=0, annual_rate=0.005, years=35)
        assert result.loan_amount == 30_000_000


class TestTaxCredit:
    def test_default_rate(self):
        credit = calc_tax_credit_annual(30_000_000)
        assert credit == 210_000  # 30M * 0.7% = 210,000

    def test_cap_applies(self):
        credit = calc_tax_credit_annual(40_000_000)
        assert credit == 210_000  # capped

    def test_small_balance(self):
        credit = calc_tax_credit_annual(10_000_000)
        assert credit == 70_000  # 10M * 0.7% = 70,000


class TestOutstandingBalance:
    def test_year_zero(self):
        balance = approximate_outstanding_balance(30_000_000, 0.005, 35, 0)
        assert balance == 30_000_000

    def test_full_term(self):
        balance = approximate_outstanding_balance(30_000_000, 0.005, 35, 35)
        assert balance == 0

    def test_midpoint(self):
        balance = approximate_outstanding_balance(30_000_000, 0.005, 35, 17)
        assert 10_000_000 < balance < 20_000_000

    def test_zero_rate(self):
        balance = approximate_outstanding_balance(30_000_000, 0.0, 30, 15)
        assert balance == 15_000_000
