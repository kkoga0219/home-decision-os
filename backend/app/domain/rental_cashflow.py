"""Rental cashflow calculation for future rental scenario.

Effective rent = expected_rent * (1 - vacancy_rate) - management_commission
Monthly CF = effective_rent - ownership_cost
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RentalCashflowResult:
    expected_rent: int
    vacancy_loss: int
    management_commission: int
    effective_rent: int
    ownership_cost_monthly: int
    monthly_cashflow: int
    annual_cashflow: int


def calc_rental_cashflow(
    expected_rent: int,
    vacancy_rate: float,
    management_fee_rate: float,
    ownership_cost_monthly: int,
) -> RentalCashflowResult:
    """Calculate monthly rental cashflow.

    Parameters
    ----------
    expected_rent : int
        Gross monthly rent in JPY.
    vacancy_rate : float
        Assumed vacancy rate (e.g. 0.05 = 5 %).
    management_fee_rate : float
        Property-management commission rate (e.g. 0.05 = 5 %).
    ownership_cost_monthly : int
        Total monthly ownership cost (loan + mgmt + repair + tax + ins).
    """
    vacancy_loss = int(expected_rent * vacancy_rate)
    management_commission = int(expected_rent * management_fee_rate)
    effective = expected_rent - vacancy_loss - management_commission
    cf = effective - ownership_cost_monthly
    return RentalCashflowResult(
        expected_rent=expected_rent,
        vacancy_loss=vacancy_loss,
        management_commission=management_commission,
        effective_rent=effective,
        ownership_cost_monthly=ownership_cost_monthly,
        monthly_cashflow=cf,
        annual_cashflow=cf * 12,
    )
