"""Add normalized study programmes, courses, and requirement groups.

Revision ID: 20260817_0003
Revises: 20260811_0002
"""
from alembic import op
import sqlalchemy as sa

revision = "20260817_0003"
down_revision = "20260811_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "study_programs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(160), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("degree_type", sa.String(80), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("academic_year", sa.String(9)),
        sa.Column("valid_from_year", sa.Integer()),
        sa.Column("valid_to_year", sa.Integer()),
        sa.Column("introduction", sa.Text()),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_url", name="uq_study_program_source_url"),
    )
    op.create_index("ix_study_programs_slug", "study_programs", ["slug"])
    op.create_index("ix_study_programs_name", "study_programs", ["name"])

    op.create_table(
        "study_plan_sections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("program_id", sa.Integer(), sa.ForeignKey("study_programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("program_id", "name", name="uq_study_plan_section_program_name"),
    )
    op.create_index(
        "ix_study_plan_sections_program_position", "study_plan_sections", ["program_id", "position"]
    )

    op.create_table(
        "study_plan_courses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("program_id", sa.Integer(), sa.ForeignKey("study_programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("section_id", sa.Integer(), sa.ForeignKey("study_plan_sections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_number", sa.String(16)),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("ects", sa.Numeric(5, 2)),
        sa.Column("ects_options", sa.JSON(), nullable=False),
        sa.Column("schedule", sa.Text()),
        sa.Column("source_url", sa.Text()),
        sa.Column("requirement_role", sa.String(32), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_study_plan_courses_program_course", "study_plan_courses", ["program_id", "course_number"]
    )
    op.create_index(
        "ix_study_plan_courses_section_position", "study_plan_courses", ["section_id", "position"]
    )

    op.create_table(
        "study_plan_requirements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("program_id", sa.Integer(), sa.ForeignKey("study_programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("section_id", sa.Integer(), sa.ForeignKey("study_plan_sections.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "parent_requirement_id",
            sa.Integer(),
            sa.ForeignKey("study_plan_requirements.id", ondelete="CASCADE"),
        ),
        sa.Column("requirement_type", sa.String(32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("required_ects", sa.Numeric(5, 2)),
        sa.Column("required_count", sa.Integer()),
        sa.Column("position", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_study_plan_requirements_section_position",
        "study_plan_requirements",
        ["section_id", "position"],
    )

    op.create_table(
        "study_plan_requirement_courses",
        sa.Column(
            "requirement_id",
            sa.Integer(),
            sa.ForeignKey("study_plan_requirements.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "course_id",
            sa.Integer(),
            sa.ForeignKey("study_plan_courses.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("study_plan_requirement_courses")
    op.drop_index("ix_study_plan_requirements_section_position", table_name="study_plan_requirements")
    op.drop_table("study_plan_requirements")
    op.drop_index("ix_study_plan_courses_section_position", table_name="study_plan_courses")
    op.drop_index("ix_study_plan_courses_program_course", table_name="study_plan_courses")
    op.drop_table("study_plan_courses")
    op.drop_index("ix_study_plan_sections_program_position", table_name="study_plan_sections")
    op.drop_table("study_plan_sections")
    op.drop_index("ix_study_programs_name", table_name="study_programs")
    op.drop_index("ix_study_programs_slug", table_name="study_programs")
    op.drop_table("study_programs")
