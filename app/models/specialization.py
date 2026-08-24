from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class StudySpecialization(Base):
    __tablename__ = "study_specializations"
    __table_args__ = (
        UniqueConstraint("program_id", "slug", name="uq_study_specialization_program_slug"),
        Index("ix_study_specializations_program_position", "program_id", "position"),
        Index("ix_study_specializations_name", "name"),
        Index("ix_study_specializations_source_url", "source_url"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    program_id: Mapped[int] = mapped_column(ForeignKey("study_programs.id", ondelete="CASCADE"), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    program: Mapped["StudyProgram"] = relationship(back_populates="specializations")
    courses: Mapped[list["SpecializationCourse"]] = relationship(
        back_populates="specialization", cascade="all, delete-orphan", order_by="SpecializationCourse.position"
    )
    requirements: Mapped[list["SpecializationRequirement"]] = relationship(
        back_populates="specialization",
        cascade="all, delete-orphan",
        order_by="SpecializationRequirement.position",
    )


class SpecializationCourse(Base):
    __tablename__ = "specialization_courses"
    __table_args__ = (
        Index("ix_specialization_courses_specialization_position", "specialization_id", "position"),
        Index("ix_specialization_courses_course_number", "course_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    specialization_id: Mapped[int] = mapped_column(
        ForeignKey("study_specializations.id", ondelete="CASCADE"), nullable=False
    )
    course_number: Mapped[str | None] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    ects: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    schedule: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    is_terminated: Mapped[bool] = mapped_column(nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    specialization: Mapped[StudySpecialization] = relationship(back_populates="courses")
    requirement_links: Mapped[list["SpecializationRequirementCourse"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )


class SpecializationRequirement(Base):
    __tablename__ = "specialization_requirements"
    __table_args__ = (
        Index("ix_specialization_requirements_specialization_position", "specialization_id", "position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    specialization_id: Mapped[int] = mapped_column(
        ForeignKey("study_specializations.id", ondelete="CASCADE"), nullable=False
    )
    requirement_type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    required_ects: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    required_count: Mapped[int | None] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    specialization: Mapped[StudySpecialization] = relationship(back_populates="requirements")
    course_links: Mapped[list["SpecializationRequirementCourse"]] = relationship(
        back_populates="requirement", cascade="all, delete-orphan"
    )


class SpecializationRequirementCourse(Base):
    __tablename__ = "specialization_requirement_courses"

    requirement_id: Mapped[int] = mapped_column(
        ForeignKey("specialization_requirements.id", ondelete="CASCADE"), primary_key=True
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("specialization_courses.id", ondelete="CASCADE"), primary_key=True
    )

    requirement: Mapped[SpecializationRequirement] = relationship(back_populates="course_links")
    course: Mapped[SpecializationCourse] = relationship(back_populates="requirement_links")
