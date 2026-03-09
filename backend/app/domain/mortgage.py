"""Mortgage (housing loan) calculation logic.

Uses the standard fixed-rate amortisation formula (元利均等返済):

    M = P * r * (1+r)^n / ((1+r)^n - 1)

where
    P = principal (loan amount)
    r = monthly interest rate
    n = total number of payments
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MortgageResult:
    monthly_payment: int  # JPY
    annual_payment: int
    total_payment: int
    total_interest: int
    loan_amount: int
    annual_rate: float
    years: int


def calc_monthly_payment(principal: int, annual_rate: float, years: int) -> int:
    """Return monthly payment in JPY (rounded up to nearest yen).

    Parameters
    ----------
    principal : int
        Loan amount in JPY.
    annual_rate : float
        Annual interest rate as a decimal (e.g. 0.005 for 0.5 %).
    years : int
        Repayment period in years.
    """
    if principal <= 0:
        return 0
    if annual_rate <= 0:
        # Zero-interest: simple division
        return -(-principal // (years * 12))  # ceiling division

    r = annual_rate / 12
    n = years * 12
    factor = (1 + r) ** n
    monthly = principal * r * factor / (factor - 1)
    return int(monthly + 0.5)  # round to nearest yen


def calc_mortgage(
    price: int,
    down_payment: int,
    annual_rate: float,
    years: int,
) -> MortgageResult:
    """Full mortgage calculation."""
    loan_amount = price - down_payment
    monthly = calc_monthly_payment(loan_amount, annual_rate, years)
    annual = monthly * 12
    total = annual * years
    return MortgageResult(
        monthly_payment=monthly,
        annual_payment=annual,
        total_payment=total,
        total_interest=total - loan_amount,
        loan_amount=loan_amount,
        annual_rate=annual_rate,
        years=years,
    )


def calc_tax_credit_annual(
    outstanding_balance: int,
    credit_rate: float = 0.007,
    max_credit: int = 210_000,
) -> int:
    """Simplified housing-loan tax credit (住宅ローン控除) for one year.

    Parameters
    ----------
    outstanding_balance : int
        Year-end loan balance in JPY.
    credit_rate : float
        Credit rate (0.7 % = 0.007 for new builds since 2022).
    max_credit : int
        Annual cap in JPY (default 210,000 for typical new-build).
    """
    credit = int(outstanding_balance * credit_rate)
    return min(credit, max_credit)


def approximate_outstanding_balance(
    principal: int, annual_rate: float, years: int, elapsed_years: int
) -> int:
    """Approximate outstanding balance after *elapsed_years*.

    Uses the standard formula:
        B_k = P * ((1+r)^n - (1+r)^k) / ((1+r)^n - 1)
    """
    if annual_rate <= 0:
        paid = int(principal / years * elapsed_years)
        return max(principal - paid, 0)

    r = annual_rate / 12
    n = years * 12
    k = elapsed_years * 12
    factor_n = (1 + r) ** n
    factor_k = (1 + r) ** k
    balance = principal * (factor_n - factor_k) / (factor_n - 1)
    return max(int(balance + 0.5), 0)
