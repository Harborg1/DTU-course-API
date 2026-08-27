from datetime import datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, FetchedValue, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


SearchVector = Text().with_variant(TSVECTOR(), "postgresql")
StructuredJson = JSON().with_variant(JSONB(), "postgresql")
EmbeddingVector = Vector(1536).with_variant(JSON(), "sqlite")


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
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_number: Mapped[str] = mapped_column(String(16), nullable=False)
    academic_year: Mapped[str] = mapped_column(String(9), nullable=False)
    university: Mapped[str] = mapped_column(String(16), nullable=False, default="dtu")
    programme_level_code: Mapped[str | None] = mapped_column(String(64))
    teaching_language_code: Mapped[str | None] = mapped_column(String(16))
    location_code: Mapped[str | None] = mapped_column(String(64))
    study_board_code: Mapped[str | None] = mapped_column(String(32))
    ects: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    level: Mapped[str | None] = mapped_column(String(100))
    course_type: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(100))
    department: Mapped[str | None] = mapped_column(Text)
    department_code: Mapped[str | None] = mapped_column(String(16))
    period: Mapped[str | None] = mapped_column(String(100))
    schedule: Mapped[str | None] = mapped_column(Text)
    campus: Mapped[str | None] = mapped_column(Text)
    exam: Mapped[str | None] = mapped_column(Text)
    evaluation: Mapped[str | None] = mapped_column(Text)
    course_responsible: Mapped[str | None] = mapped_column(Text)
    teachers: Mapped[str | None] = mapped_column(Text)
    registration_requirements: Mapped[str | None] = mapped_column(Text)
    schedules: Mapped[list[str]] = mapped_column(StructuredJson, nullable=False, default=list)
    responsible_people: Mapped[list[dict]] = mapped_column(StructuredJson, nullable=False, default=list)
    examinations: Mapped[list[dict]] = mapped_column(StructuredJson, nullable=False, default=list)
    no_credit_with: Mapped[list[str]] = mapped_column(StructuredJson, nullable=False, default=list)
    recommended_prerequisite_course_numbers: Mapped[list[str]] = mapped_column(
        StructuredJson, nullable=False, default=list
    )
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_last_updated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    translations: Mapped[list["CourseTranslation"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="CourseTranslation.language_code",
    )

    def translation(self, language: str) -> "CourseTranslation | None":
        language_code = {"da": "da-DK", "en": "en-GB"}.get(language, language)
        return next((item for item in self.translations if item.language_code == language_code), None)

    def translated_value(self, field: str, language: str = "en") -> str | None:
        preferred = self.translation(language)
        fallback = self.translation("da" if language in {"en", "en-GB"} else "en")
        return getattr(preferred, field, None) or getattr(fallback, field, None)

    def localized_value(self, field: str, language: str) -> str | None:
        translation = self.translation(language)
        return getattr(translation, field, None)

    @property
    def title(self) -> str:
        return self.translated_value("title") or self.course_number

    @property
    def title_da(self) -> str | None:
        return self.localized_value("title", "da")

    @property
    def title_en(self) -> str | None:
        return self.localized_value("title", "en")

    @property
    def description(self) -> str | None:
        return self.translated_value("description")

    @property
    def description_da(self) -> str | None:
        return self.localized_value("description", "da")

    @property
    def description_en(self) -> str | None:
        return self.localized_value("description", "en")

    @property
    def content(self) -> str | None:
        return self.translated_value("content")

    @property
    def content_da(self) -> str | None:
        return self.localized_value("content", "da")

    @property
    def content_en(self) -> str | None:
        return self.localized_value("content", "en")

    @property
    def learning_objectives(self) -> str | None:
        return self.translated_value("learning_objectives")

    @property
    def learning_objectives_da(self) -> str | None:
        return self.localized_value("learning_objectives", "da")

    @property
    def learning_objectives_en(self) -> str | None:
        return self.localized_value("learning_objectives", "en")

    @property
    def prerequisites(self) -> str | None:
        return self.translated_value("prerequisites")

    @property
    def prerequisites_da(self) -> str | None:
        return self.localized_value("prerequisites", "da")

    @property
    def prerequisites_en(self) -> str | None:
        return self.localized_value("prerequisites", "en")

    @property
    def mandatory_prerequisites(self) -> str | None:
        return self.translated_value("mandatory_prerequisites")

    @property
    def mandatory_prerequisites_da(self) -> str | None:
        return self.localized_value("mandatory_prerequisites", "da")

    @property
    def mandatory_prerequisites_en(self) -> str | None:
        return self.localized_value("mandatory_prerequisites", "en")

    @property
    def teaching_methods(self) -> str | None:
        return self.translated_value("teaching_methods")

    @property
    def teaching_methods_da(self) -> str | None:
        return self.localized_value("teaching_methods", "da")

    @property
    def teaching_methods_en(self) -> str | None:
        return self.localized_value("teaching_methods", "en")

    @property
    def literature(self) -> str | None:
        return self.translated_value("literature")

    @property
    def literature_da(self) -> str | None:
        return self.localized_value("literature", "da")

    @property
    def literature_en(self) -> str | None:
        return self.localized_value("literature", "en")

    @property
    def remarks(self) -> str | None:
        return self.translated_value("remarks")

    @property
    def remarks_da(self) -> str | None:
        return self.localized_value("remarks", "da")

    @property
    def remarks_en(self) -> str | None:
        return self.localized_value("remarks", "en")


class CourseTranslation(Base):
    __tablename__ = "course_translations"
    __table_args__ = (
        UniqueConstraint("course_id", "language_code", name="uq_course_translation_language"),
        Index("ix_course_translations_language_course", "language_code", "course_id"),
        Index("ix_course_translations_search_vector", "search_vector", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    language_code: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)
    learning_objectives: Mapped[str | None] = mapped_column(Text)
    prerequisites: Mapped[str | None] = mapped_column(Text)
    mandatory_prerequisites: Mapped[str | None] = mapped_column(Text)
    teaching_methods: Mapped[str | None] = mapped_column(Text)
    literature: Mapped[str | None] = mapped_column(Text)
    remarks: Mapped[str | None] = mapped_column(Text)
    search_vector: Mapped[str | None] = mapped_column(
        SearchVector,
        nullable=True,
        server_default=FetchedValue(),
        server_onupdate=FetchedValue(),
    )
    embedding: Mapped[list[float] | None] = mapped_column(EmbeddingVector)
    embedding_text_hash: Mapped[str | None] = mapped_column(String(64))
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    embedding_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    course: Mapped[Course] = relationship(back_populates="translations")
