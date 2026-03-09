"""Create initial tables.

Revision ID: 001
Revises: None
Create Date: 2026-03-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "properties",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("address_text", sa.Text(), nullable=True),
        sa.Column("station_name", sa.String(100), nullable=True),
        sa.Column("walking_minutes", sa.Integer(), nullable=True),
        sa.Column("price_jpy", sa.Integer(), nullable=False),
        sa.Column("floor_area_sqm", sa.Float(), nullable=True),
        sa.Column("layout", sa.String(20), nullable=True),
        sa.Column("built_year", sa.Integer(), nullable=True),
        sa.Column("management_fee_jpy", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("repair_reserve_jpy", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("floor_number", sa.Integer(), nullable=True),
        sa.Column("total_floors", sa.Integer(), nullable=True),
        sa.Column("total_units", sa.Integer(), nullable=True),
        sa.Column("zoning_type", sa.String(50), nullable=True),
        sa.Column("hazard_flag", sa.Boolean(), nullable=True),
        sa.Column("memo", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_properties_id", "properties", ["id"])

    op.create_table(
        "loan_scenarios",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "property_id", sa.Integer(), sa.ForeignKey("properties.id"), nullable=False
        ),
        sa.Column("label", sa.String(100), nullable=True),
        sa.Column("down_payment_jpy", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("loan_amount_jpy", sa.Integer(), nullable=False),
        sa.Column("annual_interest_rate", sa.Float(), nullable=False),
        sa.Column("loan_years", sa.Integer(), nullable=False),
        sa.Column("tax_credit_rate", sa.Float(), nullable=False, server_default="0.007"),
        sa.Column("tax_credit_years", sa.Integer(), nullable=False, server_default="13"),
        sa.Column("monthly_payment_jpy", sa.Integer(), nullable=False),
        sa.Column("annual_payment_jpy", sa.Integer(), nullable=False),
        sa.Column("total_payment_jpy", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_loan_scenarios_id", "loan_scenarios", ["id"])
    op.create_index("ix_loan_scenarios_property_id", "loan_scenarios", ["property_id"])

    op.create_table(
        "rental_scenarios",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "property_id", sa.Integer(), sa.ForeignKey("properties.id"), nullable=False
        ),
        sa.Column("label", sa.String(100), nullable=True),
        sa.Column("expected_rent_jpy", sa.Integer(), nullable=False),
        sa.Column("vacancy_rate", sa.Float(), nullable=False, server_default="0.05"),
        sa.Column("management_fee_rate", sa.Float(), nullable=False, server_default="0.05"),
        sa.Column("insurance_annual_jpy", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "fixed_asset_tax_annual_jpy", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("other_cost_annual_jpy", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("monthly_net_cashflow_jpy", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_rental_scenarios_id", "rental_scenarios", ["id"])
    op.create_index("ix_rental_scenarios_property_id", "rental_scenarios", ["property_id"])

    op.create_table(
        "exit_scores",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "property_id", sa.Integer(), sa.ForeignKey("properties.id"), nullable=False
        ),
        sa.Column("station_score", sa.Integer(), nullable=False),
        sa.Column("size_score", sa.Integer(), nullable=False),
        sa.Column("layout_score", sa.Integer(), nullable=False),
        sa.Column("age_score", sa.Integer(), nullable=False),
        sa.Column("zoning_score", sa.Integer(), nullable=False),
        sa.Column("hazard_score", sa.Integer(), nullable=False),
        sa.Column("liquidity_score", sa.Integer(), nullable=False),
        sa.Column("total_score", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_exit_scores_id", "exit_scores", ["id"])
    op.create_index("ix_exit_scores_property_id", "exit_scores", ["property_id"])


def downgrade() -> None:
    op.drop_table("exit_scores")
    op.drop_table("rental_scenarios")
    op.drop_table("loan_scenarios")
    op.drop_table("properties")
