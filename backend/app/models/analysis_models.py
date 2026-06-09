from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from datetime import datetime
from uuid import uuid4

from app.db.database import Base


class JobAnalysis(Base):
    __tablename__ = "job_analysis"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"))

    result: Mapped[dict] = mapped_column(JSONB)

    analyzer_version: Mapped[str | None] = mapped_column(String, default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
