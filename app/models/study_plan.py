from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class StudyProgram(Base):
    __tablename__ = "study_programs"
    __table_args__ = (
        UniqueConstraint("source_url", name="uq_study_program_source_url"),
        Index("ix_study_programs_slug", "slug"),
        Index("ix_study_programs_name", "name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(160), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    degree_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aliases: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    academic_year: Mapped[str | None] = mapped_column(String(9))
    valid_from_year: Mapped[int | None] = mapped_column(Integer)
    valid_to_year: Mapped[int | None] = mapped_column(Integer)
    introduction: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    sections: Mapped[list["StudyPlanSection"]] = relationship(
        back_populates="program", cascade="all, delete-orphan", order_by="StudyPlanSection.position"
    )
    courses: Mapped[list["StudyPlanCourse"]] = relationship(
        back_populates="program"
    )
    requirements: Mapped[list["StudyPlanRequirement"]] = relationship(
        back_populates="program"
    )


class StudyPlanSection(Base):
    __tablename__ = "study_plan_sections"
    __table_args__ = (
        UniqueConstraint("program_id", "name", name="uq_study_plan_section_program_name"),
        Index("ix_study_plan_sections_program_position", "program_id", "position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    program_id: Mapped[int] = mapped_column(ForeignKey("study_programs.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    program: Mapped[StudyProgram] = relationship(back_populates="sections")
    courses: Mapped[list["StudyPlanCourse"]] = relationship(
        back_populates="section", cascade="all, delete-orphan", order_by="StudyPlanCourse.position"
    )
    requirements: Mapped[list["StudyPlanRequirement"]] = relationship(
        back_populates="section", cascade="all, delete-orphan", order_by="StudyPlanRequirement.position"
    )


class StudyPlanCourse(Base):
    __tablename__ = "study_plan_courses"
    __table_args__ = (
        Index("ix_study_plan_courses_program_course", "program_id", "course_number"),
        Index("ix_study_plan_courses_section_position", "section_id", "position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    program_id: Mapped[int] = mapped_column(ForeignKey("study_programs.id", ondelete="CASCADE"), nullable=False)
    section_id: Mapped[int] = mapped_column(ForeignKey("study_plan_sections.id", ondelete="CASCADE"), nullable=False)
    course_number: Mapped[str | None] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    ects: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    ects_options: Mapped[list[float]] = mapped_column(JSON, nullable=False, default=list)
    schedule: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    requirement_role: Mapped[str] = mapped_column(String(32), nullable=False, default="elective")
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    program: Mapped[StudyProgram] = relationship(back_populates="courses")
    section: Mapped[StudyPlanSection] = relationship(back_populates="courses")
    requirement_links: Mapped[list["StudyPlanRequirementCourse"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )


class StudyPlanRequirement(Base):
    __tablename__ = "study_plan_requirements"
    __table_args__ = (Index("ix_study_plan_requirements_section_position", "section_id", "position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    program_id: Mapped[int] = mapped_column(ForeignKey("study_programs.id", ondelete="CASCADE"), nullable=False)
    section_id: Mapped[int] = mapped_column(ForeignKey("study_plan_sections.id", ondelete="CASCADE"), nullable=False)
    parent_requirement_id: Mapped[int | None] = mapped_column(
        ForeignKey("study_plan_requirements.id", ondelete="CASCADE")
    )
    requirement_type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    required_ects: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    required_count: Mapped[int | None] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    program: Mapped[StudyProgram] = relationship(back_populates="requirements")
    section: Mapped[StudyPlanSection] = relationship(back_populates="requirements")
    parent: Mapped["StudyPlanRequirement | None"] = relationship(
        remote_side="StudyPlanRequirement.id", back_populates="children"
    )
    children: Mapped[list["StudyPlanRequirement"]] = relationship(
        back_populates="parent"
    )
    course_links: Mapped[list["StudyPlanRequirementCourse"]] = relationship(
        back_populates="requirement", cascade="all, delete-orphan"
    )


class StudyPlanRequirementCourse(Base):
    __tablename__ = "study_plan_requirement_courses"

    requirement_id: Mapped[int] = mapped_column(
        ForeignKey("study_plan_requirements.id", ondelete="CASCADE"), primary_key=True
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("study_plan_courses.id", ondelete="CASCADE"), primary_key=True
    )

    requirement: Mapped[StudyPlanRequirement] = relationship(back_populates="course_links")
    course: Mapped[StudyPlanCourse] = relationship(back_populates="requirement_links")
