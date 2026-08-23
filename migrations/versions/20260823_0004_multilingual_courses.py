"""Recreate courses for bilingual GetCourse XML.

Revision ID: 20260823_0004
Revises: 20260817_0003
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260823_0004"
down_revision = "20260817_0003"
branch_labels = None
depends_on = None


def _search_expression(language: str, suffix: str) -> str:
    return f"""
setweight(to_tsvector('{language}', coalesce(title_{suffix}, '')), 'A') ||
setweight(to_tsvector('{language}', coalesce(description_{suffix}, '')), 'B') ||
setweight(to_tsvector('{language}', coalesce(content_{suffix}, '')), 'B') ||
setweight(to_tsvector('{language}', coalesce(learning_objectives_{suffix}, '')), 'B') ||
setweight(to_tsvector('{language}', coalesce(prerequisites_{suffix}, '')), 'C') ||
setweight(to_tsvector('{language}', coalesce(mandatory_prerequisites_{suffix}, '')), 'C') ||
setweight(to_tsvector('{language}', coalesce(teaching_methods_{suffix}, '')), 'C') ||
setweight(to_tsvector('{language}', coalesce(literature_{suffix}, '')), 'D') ||
setweight(to_tsvector('{language}', coalesce(remarks_{suffix}, '')), 'D')
"""


def upgrade() -> None:
    # The old table may already have been removed manually in a development project.
    op.execute("DROP TABLE IF EXISTS courses")
    op.create_table(
        "courses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course_number", sa.String(16), nullable=False),
        sa.Column("academic_year", sa.String(9), nullable=False),
        sa.Column("university", sa.String(16), nullable=False, server_default="dtu"),
        sa.Column("programme_level_code", sa.String(64)),
        sa.Column("teaching_language_code", sa.String(16)),
        sa.Column("location_code", sa.String(64)),
        sa.Column("study_board_code", sa.String(32)),
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
        sa.Column("prerequisites_da", sa.Text()),
        sa.Column("prerequisites_en", sa.Text()),
        sa.Column("mandatory_prerequisites", sa.Text()),
        sa.Column("mandatory_prerequisites_da", sa.Text()),
        sa.Column("mandatory_prerequisites_en", sa.Text()),
        sa.Column("exam", sa.Text()),
        sa.Column("evaluation", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.Column("description_da", sa.Text()),
        sa.Column("description_en", sa.Text()),
        sa.Column("content", sa.Text()),
        sa.Column("content_da", sa.Text()),
        sa.Column("content_en", sa.Text()),
        sa.Column("learning_objectives", sa.Text()),
        sa.Column("learning_objectives_da", sa.Text()),
        sa.Column("learning_objectives_en", sa.Text()),
        sa.Column("teaching_methods", sa.Text()),
        sa.Column("teaching_methods_da", sa.Text()),
        sa.Column("teaching_methods_en", sa.Text()),
        sa.Column("literature", sa.Text()),
        sa.Column("literature_da", sa.Text()),
        sa.Column("literature_en", sa.Text()),
        sa.Column("course_responsible", sa.Text()),
        sa.Column("teachers", sa.Text()),
        sa.Column("registration_requirements", sa.Text()),
        sa.Column("remarks", sa.Text()),
        sa.Column("remarks_da", sa.Text()),
        sa.Column("remarks_en", sa.Text()),
        sa.Column(
            "schedules",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "responsible_people",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "examinations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "no_credit_with",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_last_updated", sa.DateTime(timezone=True)),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column(
            "search_vector_da",
            postgresql.TSVECTOR(),
            sa.Computed(_search_expression("danish", "da"), persisted=True),
        ),
        sa.Column(
            "search_vector_en",
            postgresql.TSVECTOR(),
            sa.Computed(_search_expression("english", "en"), persisted=True),
        ),
        sa.UniqueConstraint("course_number", "academic_year", name="uq_course_number_academic_year"),
    )
    for column in (
        "course_number",
        "academic_year",
        "ects",
        "level",
        "period",
        "schedule",
        "department",
        "language",
    ):
        op.create_index(f"ix_courses_{column}", "courses", [column])
    op.create_index(
        "ix_courses_search_vector_da",
        "courses",
        ["search_vector_da"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_courses_search_vector_en",
        "courses",
        ["search_vector_en"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_table("courses")
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
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "setweight(to_tsvector('simple', coalesce(title, '')), 'A') || "
                "setweight(to_tsvector('simple', coalesce(description, '')), 'B') || "
                "setweight(to_tsvector('simple', coalesce(content, '')), 'B') || "
                "setweight(to_tsvector('simple', coalesce(learning_objectives, '')), 'C') || "
                "setweight(to_tsvector('simple', coalesce(prerequisites, '')), 'C')",
                persisted=True,
            ),
        ),
        sa.UniqueConstraint("course_number", "academic_year", name="uq_course_number_academic_year"),
    )
    op.create_index("ix_courses_search_vector", "courses", ["search_vector"], postgresql_using="gin")
