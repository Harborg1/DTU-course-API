"""Create courses and import failures.

Revision ID: 20260811_0001
Revises:
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260811_0001"
down_revision = None
branch_labels = None
depends_on = None

SEARCH_EXPRESSION = """
setweight(to_tsvector('simple', coalesce(title, '')), 'A') ||
setweight(to_tsvector('simple', coalesce(description, '')), 'B') ||
setweight(to_tsvector('simple', coalesce(content, '')), 'B') ||
setweight(to_tsvector('simple', coalesce(learning_objectives, '')), 'C') ||
setweight(to_tsvector('simple', coalesce(prerequisites, '')), 'C')
"""


def upgrade() -> None:
    op.create_table(
        "courses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course_number", sa.String(16), nullable=False),
        sa.Column("academic_year", sa.String(9), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("title_da", sa.Text()),
        sa.Column("title_en", sa.Text()),
        sa.Column("ects", sa.Numeric(5, 2)),
        sa.Column("level", sa.String(100)),
        sa.Column("course_type", sa.Text()),
        sa.Column("language", sa.String(100)),
        sa.Column("department", sa.Text()),
        sa.Column("department_code", sa.String(16)),
        sa.Column("period", sa.String(100)),
        sa.Column("schedule", sa.Text()),
        sa.Column("campus", sa.Text()),
        sa.Column("prerequisites", sa.Text()),
        sa.Column("mandatory_prerequisites", sa.Text()),
        sa.Column("exam", sa.Text()),
        sa.Column("evaluation", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.Column("content", sa.Text()),
        sa.Column("learning_objectives", sa.Text()),
        sa.Column("course_responsible", sa.Text()),
        sa.Column("teachers", sa.Text()),
        sa.Column("registration_requirements", sa.Text()),
        sa.Column("remarks", sa.Text()),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_last_updated", sa.DateTime(timezone=True)),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("search_vector", postgresql.TSVECTOR(), sa.Computed(SEARCH_EXPRESSION, persisted=True)),
        sa.UniqueConstraint("course_number", "academic_year", name="uq_course_number_academic_year"),
    )
    for column in ("course_number", "academic_year", "ects", "level", "period", "schedule", "department", "language"):
        op.create_index(f"ix_courses_{column}", "courses", [column])
    op.create_index("ix_courses_search_vector", "courses", ["search_vector"], postgresql_using="gin")

    op.create_table(
        "import_failures",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course_number", sa.String(16), nullable=False),
        sa.Column("academic_year", sa.String(9), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("error_type", sa.String(100), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("first_failed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_failed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("course_number", "academic_year", name="uq_failure_course_year"),
    )
    op.create_index("ix_import_failures_academic_year", "import_failures", ["academic_year"])


def downgrade() -> None:
    op.drop_table("import_failures")
    op.drop_index("ix_courses_search_vector", table_name="courses")
    op.drop_table("courses")

