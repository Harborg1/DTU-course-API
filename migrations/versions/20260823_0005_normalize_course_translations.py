"""Move localized course text into course_translations.

Revision ID: 20260823_0005
Revises: 20260823_0004
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260823_0005"
down_revision = "20260823_0004"
branch_labels = None
depends_on = None


def _search_expression() -> str:
    fields = (
        ("title", "A"),
        ("description", "B"),
        ("content", "B"),
        ("learning_objectives", "B"),
        ("prerequisites", "C"),
        ("mandatory_prerequisites", "C"),
        ("teaching_methods", "C"),
        ("literature", "D"),
        ("remarks", "D"),
    )

    def document(configuration: str) -> str:
        return " ||\n".join(
            f"setweight(to_tsvector('{configuration}', coalesce({field}, '')), '{weight}')"
            for field, weight in fields
        )

    return f"""
CASE WHEN language_code = 'da-DK' THEN
{document('danish')}
ELSE
{document('english')}
END
"""


def _wide_search_expression(configuration: str, suffix: str) -> str:
    weights = (
        ("title", "A"),
        ("description", "B"),
        ("content", "B"),
        ("learning_objectives", "B"),
        ("prerequisites", "C"),
        ("mandatory_prerequisites", "C"),
        ("teaching_methods", "C"),
        ("literature", "D"),
        ("remarks", "D"),
    )
    return " ||\n".join(
        f"setweight(to_tsvector('{configuration}', coalesce({field}_{suffix}, '')), '{weight}')"
        for field, weight in weights
    )


def _create_core_table(name: str) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course_number", sa.String(16), nullable=False),
        sa.Column("academic_year", sa.String(9), nullable=False),
        sa.Column("university", sa.String(16), nullable=False, server_default="dtu"),
        sa.Column("programme_level_code", sa.String(64)),
        sa.Column("teaching_language_code", sa.String(16)),
        sa.Column("location_code", sa.String(64)),
        sa.Column("study_board_code", sa.String(32)),
        sa.Column("ects", sa.Numeric(5, 2)),
        sa.Column("level", sa.String(100)),
        sa.Column("course_type", sa.Text()),
        sa.Column("language", sa.String(100)),
        sa.Column("department", sa.Text()),
        sa.Column("department_code", sa.String(16)),
        sa.Column("period", sa.String(100)),
        sa.Column("schedule", sa.Text()),
        sa.Column("campus", sa.Text()),
        sa.Column("exam", sa.Text()),
        sa.Column("evaluation", sa.Text()),
        sa.Column("course_responsible", sa.Text()),
        sa.Column("teachers", sa.Text()),
        sa.Column("registration_requirements", sa.Text()),
        sa.Column(
            "schedules", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "responsible_people", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "examinations", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "no_credit_with", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_last_updated", sa.DateTime(timezone=True)),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.UniqueConstraint("course_number", "academic_year", name="uq_courses_v2_number_year"),
    )


def upgrade() -> None:
    _create_core_table("courses_v2")
    op.create_table(
        "course_translations_v2",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "course_id", sa.Integer(),
            sa.ForeignKey("courses_v2.id", ondelete="CASCADE", name="fk_course_translations_v2_course"),
            nullable=False,
        ),
        sa.Column("language_code", sa.String(16), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("content", sa.Text()),
        sa.Column("learning_objectives", sa.Text()),
        sa.Column("prerequisites", sa.Text()),
        sa.Column("mandatory_prerequisites", sa.Text()),
        sa.Column("teaching_methods", sa.Text()),
        sa.Column("literature", sa.Text()),
        sa.Column("remarks", sa.Text()),
        sa.Column(
            "search_vector", postgresql.TSVECTOR(),
            sa.Computed(_search_expression(), persisted=True),
        ),
        sa.UniqueConstraint(
            "course_id", "language_code", name="uq_course_translations_v2_language"
        ),
    )

    core_columns = (
        "id, course_number, academic_year, university, programme_level_code, "
        "teaching_language_code, location_code, study_board_code, ects, level, "
        "course_type, language, department, department_code, period, schedule, campus, "
        "exam, evaluation, course_responsible, teachers, registration_requirements, "
        "schedules, responsible_people, examinations, no_credit_with, source_url, "
        "source_last_updated, imported_at, updated_at, content_hash"
    )
    op.execute(f"INSERT INTO courses_v2 ({core_columns}) SELECT {core_columns} FROM courses")
    op.execute(
        """
        INSERT INTO course_translations_v2 (
            course_id, language_code, title, description, content, learning_objectives,
            prerequisites, mandatory_prerequisites, teaching_methods, literature, remarks
        )
        SELECT
            id, 'da-DK', coalesce(title_da, title_en, title), description_da, content_da,
            learning_objectives_da, prerequisites_da, mandatory_prerequisites_da,
            teaching_methods_da, literature_da, remarks_da
        FROM courses
        UNION ALL
        SELECT
            id, 'en-GB', coalesce(title_en, title_da, title), description_en, content_en,
            learning_objectives_en, prerequisites_en, mandatory_prerequisites_en,
            teaching_methods_en, literature_en, remarks_en
        FROM courses
        """
    )
    op.execute(
        """
        DO $$
        DECLARE course_count bigint;
        DECLARE copied_course_count bigint;
        DECLARE translation_count bigint;
        BEGIN
            SELECT count(*) INTO course_count FROM courses;
            SELECT count(*) INTO copied_course_count FROM courses_v2;
            SELECT count(*) INTO translation_count FROM course_translations_v2;
            IF copied_course_count <> course_count THEN
                RAISE EXCEPTION 'course copy validation failed: % <> %', copied_course_count, course_count;
            END IF;
            IF translation_count <> course_count * 2 THEN
                RAISE EXCEPTION 'translation validation failed: % <> %', translation_count, course_count * 2;
            END IF;
        END $$
        """
    )

    op.drop_table("courses")
    op.rename_table("courses_v2", "courses")
    op.rename_table("course_translations_v2", "course_translations")

    op.execute("ALTER TABLE courses RENAME CONSTRAINT courses_v2_pkey TO courses_pkey")
    op.execute(
        "ALTER TABLE courses RENAME CONSTRAINT uq_courses_v2_number_year "
        "TO uq_course_number_academic_year"
    )
    op.execute(
        "ALTER TABLE course_translations RENAME CONSTRAINT course_translations_v2_pkey "
        "TO course_translations_pkey"
    )
    op.execute(
        "ALTER TABLE course_translations RENAME CONSTRAINT uq_course_translations_v2_language "
        "TO uq_course_translation_language"
    )
    op.execute(
        "ALTER TABLE course_translations RENAME CONSTRAINT fk_course_translations_v2_course "
        "TO fk_course_translations_course"
    )
    op.execute("ALTER SEQUENCE courses_v2_id_seq RENAME TO courses_id_seq")
    op.execute(
        "ALTER SEQUENCE course_translations_v2_id_seq RENAME TO course_translations_id_seq"
    )
    op.execute(
        "SELECT setval(pg_get_serial_sequence('courses', 'id'), "
        "coalesce((SELECT max(id) FROM courses), 1), true)"
    )

    for column in (
        "course_number", "academic_year", "ects", "level", "period", "schedule",
        "department", "language",
    ):
        op.create_index(f"ix_courses_{column}", "courses", [column])
    op.create_index(
        "ix_course_translations_language_course",
        "course_translations",
        ["language_code", "course_id"],
    )
    op.create_index(
        "ix_course_translations_search_vector",
        "course_translations",
        ["search_vector"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    translated_fields = (
        "description", "content", "learning_objectives", "prerequisites",
        "mandatory_prerequisites", "teaching_methods", "literature", "remarks",
    )
    op.add_column("courses", sa.Column("title", sa.Text()))
    op.add_column("courses", sa.Column("title_da", sa.Text()))
    op.add_column("courses", sa.Column("title_en", sa.Text()))
    for field in translated_fields:
        op.add_column("courses", sa.Column(field, sa.Text()))
        op.add_column("courses", sa.Column(f"{field}_da", sa.Text()))
        op.add_column("courses", sa.Column(f"{field}_en", sa.Text()))

    assignments = [
        "title_da = da.title",
        "title_en = en.title",
        "title = coalesce(en.title, da.title, c.course_number)",
    ]
    for field in translated_fields:
        assignments.extend(
            (
                f"{field}_da = da.{field}",
                f"{field}_en = en.{field}",
                f"{field} = coalesce(en.{field}, da.{field})",
            )
        )
    op.execute(
        "UPDATE courses AS c SET "
        + ", ".join(assignments)
        + " FROM course_translations AS da, course_translations AS en "
        "WHERE da.course_id = c.id AND da.language_code = 'da-DK' "
        "AND en.course_id = c.id AND en.language_code = 'en-GB'"
    )
    op.alter_column("courses", "title", nullable=False)
    op.add_column(
        "courses",
        sa.Column(
            "search_vector_da", postgresql.TSVECTOR(),
            sa.Computed(_wide_search_expression("danish", "da"), persisted=True),
        ),
    )
    op.add_column(
        "courses",
        sa.Column(
            "search_vector_en", postgresql.TSVECTOR(),
            sa.Computed(_wide_search_expression("english", "en"), persisted=True),
        ),
    )
    op.create_index(
        "ix_courses_search_vector_da", "courses", ["search_vector_da"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_courses_search_vector_en", "courses", ["search_vector_en"],
        postgresql_using="gin",
    )
    op.drop_table("course_translations")
