from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ImportFailure(Base):
    __tablename__ = "import_failures"
    __table_args__ = (
        UniqueConstraint("course_number", "academic_year", name="uq_failure_course_year"),
        Index("ix_import_failures_academic_year", "academic_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_number: Mapped[str] = mapped_column(String(16), nullable=False)
    academic_year: Mapped[str] = mapped_column(String(9), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    error_type: Mapped[str] = mapped_column(String(100), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(default=1, nullable=False)
    first_failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

