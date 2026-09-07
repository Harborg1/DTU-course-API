"""Add normalized study specializations and course requirements.

Revision ID: 20260824_0007
Revises: 20260823_0006
"""

from alembic import op
import sqlalchemy as sa


revision = "20260824_0007"
down_revision = "20260823_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "study_specializations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("program_id", sa.Integer(), sa.ForeignKey("study_programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slug", sa.String(180), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("program_id", "slug", name="uq_study_specialization_program_slug"),
    )
    op.create_index(
        "ix_study_specializations_program_position", "study_specializations", ["program_id", "position"]
    )
    op.create_index("ix_study_specializations_name", "study_specializations", ["name"])
    op.create_index("ix_study_specializations_source_url", "study_specializations", ["source_url"])

    op.create_table(
        "specialization_courses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "specialization_id",
            sa.Integer(),
            sa.ForeignKey("study_specializations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("course_number", sa.String(16)),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("ects", sa.Numeric(5, 2)),
        sa.Column("schedule", sa.Text()),
        sa.Column("source_url", sa.Text()),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("is_terminated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("position", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_specialization_courses_specialization_position",
        "specialization_courses",
        ["specialization_id", "position"],
    )
    op.create_index("ix_specialization_courses_course_number", "specialization_courses", ["course_number"])

    op.create_table(
        "specialization_requirements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "specialization_id",
            sa.Integer(),
            sa.ForeignKey("study_specializations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("requirement_type", sa.String(32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("required_ects", sa.Numeric(5, 2)),
        sa.Column("required_count", sa.Integer()),
        sa.Column("position", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_specialization_requirements_specialization_position",
        "specialization_requirements",
        ["specialization_id", "position"],
    )

    op.create_table(
        "specialization_requirement_courses",
        sa.Column(
            "requirement_id",
            sa.Integer(),
            sa.ForeignKey("specialization_requirements.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "course_id",
            sa.Integer(),
            sa.ForeignKey("specialization_courses.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("specialization_requirement_courses")
    op.drop_index(
        "ix_specialization_requirements_specialization_position", table_name="specialization_requirements"
    )
    op.drop_table("specialization_requirements")
    op.drop_index("ix_specialization_courses_course_number", table_name="specialization_courses")
    op.drop_index(
        "ix_specialization_courses_specialization_position", table_name="specialization_courses"
    )
    op.drop_table("specialization_courses")
    op.drop_index("ix_study_specializations_source_url", table_name="study_specializations")
    op.drop_index("ix_study_specializations_name", table_name="study_specializations")
    op.drop_index("ix_study_specializations_program_position", table_name="study_specializations")
    op.drop_table("study_specializations")
