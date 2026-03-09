"""Pydantic request / response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Property
# ---------------------------------------------------------------------------

class PropertyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    source_url: str | None = None
    address_text: str | None = None
    station_name: str | None = None
    walking_minutes: int | None = Field(None, ge=0)
    price_jpy: int = Field(..., gt=0)
    floor_area_sqm: float | None = Field(None, gt=0)
    layout: str | None = None
    built_year: int | None = Field(None, ge=1950, le=2030)
    management_fee_jpy: int | None = Field(0, ge=0)
    repair_reserve_jpy: int | None = Field(0, ge=0)
    floor_number: int | None = None
    total_floors: int | None = None
    total_units: int | None = None
    zoning_type: str | None = None
    hazard_flag: bool | None = None
    memo: str | None = None


class PropertyUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    source_url: str | None = None
    address_text: str | None = None
    station_name: str | None = None
    walking_minutes: int | None = Field(None, ge=0)
    price_jpy: int | None = Field(None, gt=0)
    floor_area_sqm: float | None = Field(None, gt=0)
    layout: str | None = None
    built_year: int | None = Field(None, ge=1950, le=2030)
    management_fee_jpy: int | None = Field(None, ge=0)
    repair_reserve_jpy: int | None = Field(None, ge=0)
    floor_number: int | None = None
    total_floors: int | None = None
    total_units: int | None = None
    zoning_type: str | None = None
    hazard_flag: bool | None = None
    memo: str | None = None


class PropertyRead(BaseModel):
    id: int
    name: str
    source_url: str | None = None
    address_text: str | None = None
    station_name: str | None = None
    walking_minutes: int | None = None
    price_jpy: int
    floor_area_sqm: float | None = None
    layout: str | None = None
    built_year: int | None = None
    management_fee_jpy: int | None = None
    repair_reserve_jpy: int | None = None
    floor_number: int | None = None
    total_floors: int | None = None
    total_units: int | None = None
    zoning_type: str | None = None
    hazard_flag: bool | None = None
    memo: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Loan Scenario
# ---------------------------------------------------------------------------

class LoanScenarioCreate(BaseModel):
    label: str | None = None
    down_payment_jpy: int = Field(0, ge=0)
    annual_interest_rate: float = Field(..., ge=0, le=0.2)
    loan_years: int = Field(..., ge=1, le=50)
    tax_credit_rate: float = Field(0.007, ge=0, le=0.05)
    tax_credit_years: int = Field(13, ge=0, le=20)


class LoanScenarioRead(BaseModel):
    id: int
    property_id: int
    label: str | None = None
    down_payment_jpy: int
    loan_amount_jpy: int
    annual_interest_rate: float
    loan_years: int
    tax_credit_rate: float
    tax_credit_years: int
    monthly_payment_jpy: int
    annual_payment_jpy: int
    total_payment_jpy: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Rental Scenario
# ---------------------------------------------------------------------------

class RentalScenarioCreate(BaseModel):
    label: str | None = None
    expected_rent_jpy: int = Field(..., gt=0)
    vacancy_rate: float = Field(0.05, ge=0, le=1)
    management_fee_rate: float = Field(0.05, ge=0, le=1)
    insurance_annual_jpy: int = Field(0, ge=0)
    fixed_asset_tax_annual_jpy: int = Field(0, ge=0)
    other_cost_annual_jpy: int = Field(0, ge=0)


class RentalScenarioRead(BaseModel):
    id: int
    property_id: int
    label: str | None = None
    expected_rent_jpy: int
    vacancy_rate: float
    management_fee_rate: float
    insurance_annual_jpy: int
    fixed_asset_tax_annual_jpy: int
    other_cost_annual_jpy: int
    monthly_net_cashflow_jpy: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Exit Score
# ---------------------------------------------------------------------------

class ExitScoreRead(BaseModel):
    id: int
    property_id: int
    station_score: int
    size_score: int
    layout_score: int
    age_score: int
    zoning_score: int
    hazard_score: int
    liquidity_score: int
    total_score: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

class ComparisonRequest(BaseModel):
    property_ids: list[int] = Field(..., min_length=2, max_length=10)


class PropertySummary(BaseModel):
    property: PropertyRead
    loan_scenarios: list[LoanScenarioRead] = []
    rental_scenarios: list[RentalScenarioRead] = []
    exit_score: ExitScoreRead | None = None


class ComparisonResponse(BaseModel):
    properties: list[PropertySummary]
