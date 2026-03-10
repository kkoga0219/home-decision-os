"""SQLAlchemy ORM models."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Property(Base):
    __tablename__ = "properties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    station_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    walking_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_jpy: Mapped[int] = mapped_column(Integer)
    floor_area_sqm: Mapped[float | None] = mapped_column(Float, nullable=True)
    layout: Mapped[str | None] = mapped_column(String(20), nullable=True)
    built_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    management_fee_jpy: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    repair_reserve_jpy: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    floor_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_floors: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    zoning_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    hazard_flag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    loan_scenarios: Mapped[list["LoanScenario"]] = relationship(
        back_populates="property", cascade="all, delete-orphan"
    )
    rental_scenarios: Mapped[list["RentalScenario"]] = relationship(
        back_populates="property", cascade="all, delete-orphan"
    )
    exit_scores: Mapped[list["ExitScore"]] = relationship(
        back_populates="property", cascade="all, delete-orphan"
    )


class LoanScenario(Base):
    __tablename__ = "loan_scenarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    property_id: Mapped[int] = mapped_column(Integer, ForeignKey("properties.id"), index=True)
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    down_payment_jpy: Mapped[int] = mapped_column(Integer, default=0)
    loan_amount_jpy: Mapped[int] = mapped_column(Integer)
    annual_interest_rate: Mapped[float] = mapped_column(Float)
    loan_years: Mapped[int] = mapped_column(Integer)
    tax_credit_rate: Mapped[float] = mapped_column(Float, default=0.007)
    tax_credit_years: Mapped[int] = mapped_column(Integer, default=13)
    monthly_payment_jpy: Mapped[int] = mapped_column(Integer)
    annual_payment_jpy: Mapped[int] = mapped_column(Integer)
    total_payment_jpy: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    property: Mapped["Property"] = relationship(back_populates="loan_scenarios")


class RentalScenario(Base):
    __tablename__ = "rental_scenarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    property_id: Mapped[int] = mapped_column(Integer, ForeignKey("properties.id"), index=True)
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expected_rent_jpy: Mapped[int] = mapped_column(Integer)
    vacancy_rate: Mapped[float] = mapped_column(Float, default=0.05)
    management_fee_rate: Mapped[float] = mapped_column(Float, default=0.05)
    insurance_annual_jpy: Mapped[int] = mapped_column(Integer, default=0)
    fixed_asset_tax_annual_jpy: Mapped[int] = mapped_column(Integer, default=0)
    other_cost_annual_jpy: Mapped[int] = mapped_column(Integer, default=0)
    monthly_net_cashflow_jpy: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    property: Mapped["Property"] = relationship(back_populates="rental_scenarios")


class ExitScore(Base):
    __tablename__ = "exit_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    property_id: Mapped[int] = mapped_column(Integer, ForeignKey("properties.id"), index=True)
    station_score: Mapped[int] = mapped_column(Integer)
    size_score: Mapped[int] = mapped_column(Integer)
    layout_score: Mapped[int] = mapped_column(Integer)
    age_score: Mapped[int] = mapped_column(Integer)
    zoning_score: Mapped[int] = mapped_column(Integer)
    hazard_score: Mapped[int] = mapped_column(Integer)
    liquidity_score: Mapped[int] = mapped_column(Integer)
    total_score: Mapped[int] = mapped_column(Integer)
    assessment: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    property: Mapped["Property"] = relationship(back_populates="exit_scores")
