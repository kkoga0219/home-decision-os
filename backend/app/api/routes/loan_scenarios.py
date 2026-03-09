"""Loan scenario endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.domain.mortgage import calc_mortgage
from app.repositories import property_repo
from app.schemas.property import LoanScenarioCreate, LoanScenarioRead

router = APIRouter(prefix="/properties/{property_id}/loan-scenarios", tags=["loan-scenarios"])


@router.post("", response_model=LoanScenarioRead, status_code=201)
def create(property_id: int, body: LoanScenarioCreate, db: Session = Depends(get_db)):
    prop = property_repo.get_property(db, property_id)
    if prop is None:
        raise HTTPException(404, "Property not found")

    result = calc_mortgage(
        price=prop.price_jpy,
        down_payment=body.down_payment_jpy,
        annual_rate=body.annual_interest_rate,
        years=body.loan_years,
    )
    scenario = property_repo.create_loan_scenario(
        db,
        property_id=property_id,
        label=body.label,
        down_payment_jpy=body.down_payment_jpy,
        loan_amount_jpy=result.loan_amount,
        annual_interest_rate=body.annual_interest_rate,
        loan_years=body.loan_years,
        tax_credit_rate=body.tax_credit_rate,
        tax_credit_years=body.tax_credit_years,
        monthly_payment_jpy=result.monthly_payment,
        annual_payment_jpy=result.annual_payment,
        total_payment_jpy=result.total_payment,
    )
    return scenario


@router.get("", response_model=list[LoanScenarioRead])
def list_all(property_id: int, db: Session = Depends(get_db)):
    return property_repo.list_loan_scenarios(db, property_id)
