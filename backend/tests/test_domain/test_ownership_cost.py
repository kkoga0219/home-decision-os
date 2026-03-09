"""Tests for ownership cost calculation."""

from app.domain.ownership_cost import calc_net_monthly_cost, calc_ownership_cost


class TestOwnershipCost:
    def test_basic(self):
        result = calc_ownership_cost(
            monthly_loan_payment=80_000,
            management_fee=15_000,
            repair_reserve=12_000,
            property_tax_annual=120_000,
            insurance_annual=24_000,
            other_annual=12_000,
        )
        # 80000 + 15000 + 12000 + 10000 + 2000 + 1000 = 120000
        assert result.monthly_total == 120_000
        assert result.annual_total == 120_000 * 12

    def test_loan_only(self):
        result = calc_ownership_cost(
            monthly_loan_payment=80_000,
            management_fee=0,
            repair_reserve=0,
        )
        assert result.monthly_total == 80_000

    def test_no_loan(self):
        result = calc_ownership_cost(
            monthly_loan_payment=0,
            management_fee=15_000,
            repair_reserve=12_000,
        )
        assert result.monthly_total == 27_000


class TestNetMonthlyCost:
    def test_with_credit(self):
        net = calc_net_monthly_cost(120_000, tax_credit_annual=120_000)
        assert net == 110_000  # 120000 - 10000

    def test_no_credit(self):
        net = calc_net_monthly_cost(120_000, tax_credit_annual=0)
        assert net == 120_000
