"""Add import run audit records.

Revision ID: 20260811_0002
Revises: 20260811_0001
"""
from alembic import op
import sqlalchemy as sa

revision = "20260811_0002"
down_revision = "20260811_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("academic_year", sa.String(9), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("courses_discovered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("courses_imported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("courses_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("courses_unchanged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("courses_failed", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_import_runs_academic_year_status", "import_runs", ["academic_year", "status"])


def downgrade() -> None:
    op.drop_table("import_runs")
