from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, FetchedValue, Index, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

SearchVector = Text().with_variant(TSVECTOR(), "postgresql")


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (
        UniqueConstraint("course_number", "academic_year", name="uq_course_number_academic_year"),
        Index("ix_courses_course_number", "course_number"),
        Index("ix_courses_academic_year", "academic_year"),
        Index("ix_courses_ects", "ects"),
        Index("ix_courses_level", "level"),
        Index("ix_courses_period", "period"),
        Index("ix_courses_schedule", "schedule"),
        Index("ix_courses_department", "department"),
        Index("ix_courses_language", "language"),
        Index("ix_courses_search_vector", "search_vector", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_number: Mapped[str] = mapped_column(String(16), nullable=False)
    academic_year: Mapped[str] = mapped_column(String(9), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    title_da: Mapped[str | None] = mapped_column(Text)
    title_en: Mapped[str | None] = mapped_column(Text)
    ects: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    level: Mapped[str | None] = mapped_column(String(100))
    course_type: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(100))
    department: Mapped[str | None] = mapped_column(Text)
    department_code: Mapped[str | None] = mapped_column(String(16))
    period: Mapped[str | None] = mapped_column(String(100))
    schedule: Mapped[str | None] = mapped_column(Text)
    campus: Mapped[str | None] = mapped_column(Text)
    prerequisites: Mapped[str | None] = mapped_column(Text)
    mandatory_prerequisites: Mapped[str | None] = mapped_column(Text)
    exam: Mapped[str | None] = mapped_column(Text)
    evaluation: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)
    learning_objectives: Mapped[str | None] = mapped_column(Text)
    course_responsible: Mapped[str | None] = mapped_column(Text)
    teachers: Mapped[str | None] = mapped_column(Text)
    registration_requirements: Mapped[str | None] = mapped_column(Text)
    remarks: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_last_updated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    search_vector: Mapped[str | None] = mapped_column(
        SearchVector, nullable=True, server_default=FetchedValue(), server_onupdate=FetchedValue()
    )
