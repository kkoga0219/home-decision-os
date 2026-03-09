"""Comparison endpoint – returns multiple properties side by side."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories import property_repo
from app.schemas.property import (
    ComparisonRequest,
    ComparisonResponse,
    ExitScoreRead,
    LoanScenarioRead,
    PropertyRead,
    PropertySummary,
    RentalScenarioRead,
)

router = APIRouter(prefix="/comparison", tags=["comparison"])


@router.post("", response_model=ComparisonResponse)
def compare(body: ComparisonRequest, db: Session = Depends(get_db)):
    summaries: list[PropertySummary] = []
    for pid in body.property_ids:
        prop = property_repo.get_property_with_relations(db, pid)
        if prop is None:
            raise HTTPException(404, f"Property {pid} not found")

        latest_exit = (
            max(prop.exit_scores, key=lambda e: e.created_at) if prop.exit_scores else None
        )
        summaries.append(
            PropertySummary(
                property=PropertyRead.model_validate(prop),
                loan_scenarios=[LoanScenarioRead.model_validate(l) for l in prop.loan_scenarios],
                rental_scenarios=[
                    RentalScenarioRead.model_validate(r) for r in prop.rental_scenarios
                ],
                exit_score=ExitScoreRead.model_validate(latest_exit) if latest_exit else None,
            )
        )
    return ComparisonResponse(properties=summaries)
