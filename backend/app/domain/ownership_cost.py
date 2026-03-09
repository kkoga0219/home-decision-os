"""Ownership cost calculation.

Monthly ownership cost = loan payment + management fee + repair reserve
    + property tax / 12 + insurance / 12 + other annual / 12
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OwnershipCostResult:
    monthly_loan_payment: int
    management_fee: int
    repair_reserve: int
    monthly_property_tax: int
    monthly_insurance: int
    monthly_other: int
    monthly_total: int
    annual_total: int


def calc_ownership_cost(
    monthly_loan_payment: int,
    management_fee: int,
    repair_reserve: int,
    property_tax_annual: int = 0,
    insurance_annual: int = 0,
    other_annual: int = 0,
) -> OwnershipCostResult:
    """Calculate total monthly / annual ownership costs."""
    monthly_tax = property_tax_annual // 12
    monthly_ins = insurance_annual // 12
    monthly_oth = other_annual // 12

    total = (
        monthly_loan_payment
        + management_fee
        + repair_reserve
        + monthly_tax
        + monthly_ins
        + monthly_oth
    )
    return OwnershipCostResult(
        monthly_loan_payment=monthly_loan_payment,
        management_fee=management_fee,
        repair_reserve=repair_reserve,
        monthly_property_tax=monthly_tax,
        monthly_insurance=monthly_ins,
        monthly_other=monthly_oth,
        monthly_total=total,
        annual_total=total * 12,
    )


def calc_net_monthly_cost(
    ownership_monthly: int,
    tax_credit_annual: int = 0,
) -> int:
    """Ownership cost after housing-loan tax credit deduction (月次実質負担)."""
    return ownership_monthly - tax_credit_annual // 12
