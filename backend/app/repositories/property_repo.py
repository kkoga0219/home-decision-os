"""CRUD repository for Property and related models."""

from sqlalchemy.orm import Session, joinedload

from app.models.property import ExitScore, LoanScenario, Property, RentalScenario


# ---------------------------------------------------------------------------
# Property
# ---------------------------------------------------------------------------

def create_property(db: Session, **kwargs) -> Property:
    prop = Property(**kwargs)
    db.add(prop)
    db.commit()
    db.refresh(prop)
    return prop


def list_properties(db: Session, skip: int = 0, limit: int = 50) -> list[Property]:
    return db.query(Property).order_by(Property.updated_at.desc()).offset(skip).limit(limit).all()


def get_property(db: Session, property_id: int) -> Property | None:
    return db.query(Property).filter(Property.id == property_id).first()


def get_property_with_relations(db: Session, property_id: int) -> Property | None:
    return (
        db.query(Property)
        .options(
            joinedload(Property.loan_scenarios),
            joinedload(Property.rental_scenarios),
            joinedload(Property.exit_scores),
        )
        .filter(Property.id == property_id)
        .first()
    )


def update_property(db: Session, property_id: int, **kwargs) -> Property | None:
    prop = get_property(db, property_id)
    if prop is None:
        return None
    for k, v in kwargs.items():
        if v is not None:
            setattr(prop, k, v)
    db.commit()
    db.refresh(prop)
    return prop


def delete_property(db: Session, property_id: int) -> bool:
    prop = get_property(db, property_id)
    if prop is None:
        return False
    db.delete(prop)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Loan Scenario
# ---------------------------------------------------------------------------

def create_loan_scenario(db: Session, **kwargs) -> LoanScenario:
    scenario = LoanScenario(**kwargs)
    db.add(scenario)
    db.commit()
    db.refresh(scenario)
    return scenario


def list_loan_scenarios(db: Session, property_id: int) -> list[LoanScenario]:
    return (
        db.query(LoanScenario)
        .filter(LoanScenario.property_id == property_id)
        .order_by(LoanScenario.created_at.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# Rental Scenario
# ---------------------------------------------------------------------------

def create_rental_scenario(db: Session, **kwargs) -> RentalScenario:
    scenario = RentalScenario(**kwargs)
    db.add(scenario)
    db.commit()
    db.refresh(scenario)
    return scenario


def list_rental_scenarios(db: Session, property_id: int) -> list[RentalScenario]:
    return (
        db.query(RentalScenario)
        .filter(RentalScenario.property_id == property_id)
        .order_by(RentalScenario.created_at.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# Exit Score
# ---------------------------------------------------------------------------

def save_exit_score(db: Session, **kwargs) -> ExitScore:
    score = ExitScore(**kwargs)
    db.add(score)
    db.commit()
    db.refresh(score)
    return score


def get_latest_exit_score(db: Session, property_id: int) -> ExitScore | None:
    return (
        db.query(ExitScore)
        .filter(ExitScore.property_id == property_id)
        .order_by(ExitScore.created_at.desc())
        .first()
    )
