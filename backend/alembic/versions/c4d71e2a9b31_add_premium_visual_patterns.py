"""add premium visual patterns

Revision ID: c4d71e2a9b31
Revises: b6bd37af0df9
Create Date: 2026-05-28 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c4d71e2a9b31"
down_revision: Union[str, None] = "b6bd37af0df9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "brand_premium_visual_patterns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("brand_id", sa.Integer(), nullable=True),
        sa.Column("source_filename", sa.String(), nullable=False),
        sa.Column("patterns_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("pattern_summary", sa.Text(), nullable=True),
        sa.Column("raw_extraction", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_brand_premium_visual_patterns_id"), "brand_premium_visual_patterns", ["id"], unique=False)
    op.create_index(op.f("ix_brand_premium_visual_patterns_brand_id"), "brand_premium_visual_patterns", ["brand_id"], unique=False)
    op.create_index(op.f("ix_brand_premium_visual_patterns_source_filename"), "brand_premium_visual_patterns", ["source_filename"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_brand_premium_visual_patterns_source_filename"), table_name="brand_premium_visual_patterns")
    op.drop_index(op.f("ix_brand_premium_visual_patterns_brand_id"), table_name="brand_premium_visual_patterns")
    op.drop_index(op.f("ix_brand_premium_visual_patterns_id"), table_name="brand_premium_visual_patterns")
    op.drop_table("brand_premium_visual_patterns")
