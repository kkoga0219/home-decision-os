"""Exit score endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.domain.exit_score import calc_exit_score
from app.repositories import property_repo
from app.schemas.property import ExitScoreRead

router = APIRouter(prefix="/properties/{property_id}/exit-score", tags=["exit-score"])


@router.post("/calculate", response_model=ExitScoreRead, status_code=201)
def calculate(property_id: int, db: Session = Depends(get_db)):
    prop = property_repo.get_property(db, property_id)
    if prop is None:
        raise HTTPException(404, "Property not found")

    result = calc_exit_score(
        walking_minutes=prop.walking_minutes,
        floor_area_sqm=prop.floor_area_sqm,
        layout=prop.layout,
        built_year=prop.built_year,
        zoning_type=prop.zoning_type,
        hazard_flag=prop.hazard_flag,
        total_units=prop.total_units,
    )
    score = property_repo.save_exit_score(
        db,
        property_id=property_id,
        station_score=result.station_score,
        size_score=result.size_score,
        layout_score=result.layout_score,
        age_score=result.age_score,
        zoning_score=result.zoning_score,
        hazard_score=result.hazard_score,
        liquidity_score=result.liquidity_score,
        total_score=result.total_score,
        assessment=result.assessment,
    )
    return score


@router.get("", response_model=ExitScoreRead | None)
def get_latest(property_id: int, db: Session = Depends(get_db)):
    return property_repo.get_latest_exit_score(db, property_id)
