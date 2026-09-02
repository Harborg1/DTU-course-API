"""Store previous course numbers from the DTU catalogue.

Revision ID: 20260902_0009
Revises: 20260827_0008
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260902_0009"
down_revision = "20260827_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "courses",
        sa.Column(
            "previous_course_numbers",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.alter_column("courses", "previous_course_numbers", server_default=None)


def downgrade() -> None:
    op.drop_column("courses", "previous_course_numbers")
