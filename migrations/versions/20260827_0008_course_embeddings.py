"""Add pgvector embeddings to course translations.

Revision ID: 20260827_0008
Revises: 20260824_0007
"""

from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa


revision = "20260827_0008"
down_revision = "20260824_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column(
        "course_translations",
        sa.Column("embedding", Vector(1536), nullable=True),
    )
    op.add_column(
        "course_translations",
        sa.Column("embedding_text_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "course_translations",
        sa.Column("embedding_model", sa.String(100), nullable=True),
    )
    op.add_column(
        "course_translations",
        sa.Column("embedding_updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("course_translations", "embedding_updated_at")
    op.drop_column("course_translations", "embedding_model")
    op.drop_column("course_translations", "embedding_text_hash")
    op.drop_column("course_translations", "embedding")
