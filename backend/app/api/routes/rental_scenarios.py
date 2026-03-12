"""Rental scenario endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.domain.ownership_cost import calc_ownership_cost
from app.domain.rental_cashflow import calc_rental_cashflow
from app.repositories import property_repo
from app.schemas.property import RentalScenarioCreate, RentalScenarioRead

router = APIRouter(
    prefix="/properties/{property_id}/rental-scenarios", tags=["rental-scenarios"]
)


@router.post("", response_model=RentalScenarioRead, status_code=201)
def create(property_id: int, body: RentalScenarioCreate, db: Session = Depends(get_db)):
    prop = property_repo.get_property(db, property_id)
    if prop is None:
        raise HTTPException(404, "Property not found")

    # Use the first loan scenario if available; otherwise assume cash purchase
    loans = property_repo.list_loan_scenarios(db, property_id)
    monthly_loan = 0
    if loans:
        monthly_loan = loans[0].monthly_payment_jpy

    oc = calc_ownership_cost(
        monthly_loan_payment=monthly_loan,
        management_fee=prop.management_fee_jpy or 0,
        repair_reserve=prop.repair_reserve_jpy or 0,
        property_tax_annual=body.fixed_asset_tax_annual_jpy,
        insurance_annual=body.insurance_annual_jpy,
        other_annual=body.other_cost_annual_jpy,
    )

    rcf = calc_rental_cashflow(
        expected_rent=body.expected_rent_jpy,
        vacancy_rate=body.vacancy_rate,
        management_fee_rate=body.management_fee_rate,
        ownership_cost_monthly=oc.monthly_total,
    )

    scenario = property_repo.create_rental_scenario(
        db,
        property_id=property_id,
        label=body.label,
        expected_rent_jpy=body.expected_rent_jpy,
        vacancy_rate=body.vacancy_rate,
        management_fee_rate=body.management_fee_rate,
        insurance_annual_jpy=body.insurance_annual_jpy,
        fixed_asset_tax_annual_jpy=body.fixed_asset_tax_annual_jpy,
        other_cost_annual_jpy=body.other_cost_annual_jpy,
        monthly_net_cashflow_jpy=rcf.monthly_cashflow,
    )
    return scenario


@router.get("", response_model=list[RentalScenarioRead])
def list_all(property_id: int, db: Session = Depends(get_db)):
    return property_repo.list_rental_scenarios(db, property_id)
