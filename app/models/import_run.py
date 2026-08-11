from datetime import datetime

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ImportRun(Base):
    __tablename__ = "import_runs"
    __table_args__ = (Index("ix_import_runs_academic_year_status", "academic_year", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    academic_year: Mapped[str] = mapped_column(String(9), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    courses_discovered: Mapped[int] = mapped_column(default=0, nullable=False)
    courses_imported: Mapped[int] = mapped_column(default=0, nullable=False)
    courses_updated: Mapped[int] = mapped_column(default=0, nullable=False)
    courses_unchanged: Mapped[int] = mapped_column(default=0, nullable=False)
    courses_failed: Mapped[int] = mapped_column(default=0, nullable=False)
