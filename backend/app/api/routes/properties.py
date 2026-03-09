"""Property CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories import property_repo
from app.schemas.property import PropertyCreate, PropertyRead, PropertyUpdate

router = APIRouter(prefix="/properties", tags=["properties"])


@router.post("", response_model=PropertyRead, status_code=201)
def create(body: PropertyCreate, db: Session = Depends(get_db)):
    prop = property_repo.create_property(db, **body.model_dump())
    return prop


@router.get("", response_model=list[PropertyRead])
def list_all(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return property_repo.list_properties(db, skip=skip, limit=limit)


@router.get("/{property_id}", response_model=PropertyRead)
def get_one(property_id: int, db: Session = Depends(get_db)):
    prop = property_repo.get_property(db, property_id)
    if prop is None:
        raise HTTPException(404, "Property not found")
    return prop


@router.patch("/{property_id}", response_model=PropertyRead)
def update(property_id: int, body: PropertyUpdate, db: Session = Depends(get_db)):
    updated = property_repo.update_property(
        db, property_id, **body.model_dump(exclude_unset=True)
    )
    if updated is None:
        raise HTTPException(404, "Property not found")
    return updated


@router.delete("/{property_id}", status_code=204)
def delete(property_id: int, db: Session = Depends(get_db)):
    if not property_repo.delete_property(db, property_id):
        raise HTTPException(404, "Property not found")
