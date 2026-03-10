"""Cashflow simulation endpoints.

Provides year-by-year cashflow projection for property purchase scenarios,
including tax deductions, initial costs, and exit scenarios.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.domain.cashflow_simulator import simulate_cashflow, result_to_dict
from app.repositories import property_repo

router = APIRouter(prefix="/cashflow", tags=["cashflow"])


# ---------------------------------------------------------------------------
# Request / Response
# ---------------------------------------------------------------------------

class CashflowSimulationRequest(BaseModel):
    """直接パラメータ指定でのシミュレーション."""

    price_jpy: int = Field(..., gt=0)
    floor_area_sqm: float = Field(default=70.0, gt=0)
    built_year: int | None = None
    management_fee_jpy: int = Field(default=0, ge=0)
    repair_reserve_jpy: int = Field(default=0, ge=0)

    # ローン条件
    down_payment_jpy: int = Field(default=0, ge=0)
    annual_interest_rate: float = Field(default=0.005, ge=0, le=0.2)
    loan_years: int = Field(default=35, ge=1, le=50)

    # 住宅ローン控除
    tax_credit_rate: float = Field(default=0.007, ge=0, le=0.05)
    tax_credit_years: int | None = None
    tax_credit_max: int = Field(default=210_000, ge=0)

    # コスト
    property_tax_annual: int | None = None
    insurance_annual: int = Field(default=15_000, ge=0)

    # シナリオ
    scenario_type: str = Field(default="self_use", pattern="^(self_use|investment)$")
    expected_rent_jpy: int = Field(default=0, ge=0)
    vacancy_rate: float = Field(default=0.05, ge=0, le=1)
    pm_fee_rate: float = Field(default=0.05, ge=0, le=1)
    marginal_tax_rate: float = Field(default=0.20, ge=0, le=0.55)

    # 期間
    simulation_years: int = Field(default=35, ge=1, le=50)
    annual_price_decline_rate: float = Field(default=0.015, ge=0, le=0.1)


class PropertyCashflowRequest(BaseModel):
    """DB登録済み物件からのシミュレーション."""

    # ローン条件
    down_payment_jpy: int = Field(default=0, ge=0)
    annual_interest_rate: float = Field(default=0.005, ge=0, le=0.2)
    loan_years: int = Field(default=35, ge=1, le=50)

    # 住宅ローン控除
    tax_credit_rate: float = Field(default=0.007, ge=0, le=0.05)
    tax_credit_years: int | None = None
    tax_credit_max: int = Field(default=210_000, ge=0)

    # シナリオ
    scenario_type: str = Field(default="self_use", pattern="^(self_use|investment)$")
    expected_rent_jpy: int = Field(default=0, ge=0)
    vacancy_rate: float = Field(default=0.05, ge=0, le=1)
    pm_fee_rate: float = Field(default=0.05, ge=0, le=1)
    marginal_tax_rate: float = Field(default=0.20, ge=0, le=0.55)

    # 期間
    simulation_years: int = Field(default=35, ge=1, le=50)
    annual_price_decline_rate: float = Field(default=0.015, ge=0, le=0.1)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/simulate")
def simulate(body: CashflowSimulationRequest):
    """年次キャッシュフローシミュレーション (直接パラメータ指定)."""
    result = simulate_cashflow(
        price_jpy=body.price_jpy,
        floor_area_sqm=body.floor_area_sqm,
        built_year=body.built_year,
        management_fee_jpy=body.management_fee_jpy,
        repair_reserve_jpy=body.repair_reserve_jpy,
        down_payment_jpy=body.down_payment_jpy,
        annual_interest_rate=body.annual_interest_rate,
        loan_years=body.loan_years,
        tax_credit_rate=body.tax_credit_rate,
        tax_credit_years=body.tax_credit_years,
        tax_credit_max=body.tax_credit_max,
        property_tax_annual=body.property_tax_annual,
        insurance_annual=body.insurance_annual,
        scenario_type=body.scenario_type,
        expected_rent_jpy=body.expected_rent_jpy,
        vacancy_rate=body.vacancy_rate,
        pm_fee_rate=body.pm_fee_rate,
        marginal_tax_rate=body.marginal_tax_rate,
        simulation_years=body.simulation_years,
        annual_price_decline_rate=body.annual_price_decline_rate,
    )
    return result_to_dict(result)


@router.post("/properties/{property_id}/simulate")
def simulate_for_property(
    property_id: int,
    body: PropertyCashflowRequest,
    db: Session = Depends(get_db),
):
    """DB登録済み物件の年次キャッシュフローシミュレーション."""
    prop = property_repo.get_property(db, property_id)
    if prop is None:
        raise HTTPException(404, "Property not found")

    result = simulate_cashflow(
        price_jpy=prop.price_jpy,
        floor_area_sqm=prop.floor_area_sqm or 70.0,
        built_year=prop.built_year,
        management_fee_jpy=prop.management_fee_jpy or 0,
        repair_reserve_jpy=prop.repair_reserve_jpy or 0,
        down_payment_jpy=body.down_payment_jpy,
        annual_interest_rate=body.annual_interest_rate,
        loan_years=body.loan_years,
        tax_credit_rate=body.tax_credit_rate,
        tax_credit_years=body.tax_credit_years,
        tax_credit_max=body.tax_credit_max,
        scenario_type=body.scenario_type,
        expected_rent_jpy=body.expected_rent_jpy,
        vacancy_rate=body.vacancy_rate,
        pm_fee_rate=body.pm_fee_rate,
        marginal_tax_rate=body.marginal_tax_rate,
        simulation_years=body.simulation_years,
        annual_price_decline_rate=body.annual_price_decline_rate,
    )
    return result_to_dict(result)
