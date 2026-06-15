from sqlalchemy import (String, Text, DateTime, ForeignKey)
from sqlalchemy.dialects.postgresql import UUID, JSONB

from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from datetime import datetime
from uuid import uuid4

from app.db.database import Base

class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] =mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    source: Mapped[str] = mapped_column(String)

    company_name: Mapped[str | None] = mapped_column(String)

    role_title: Mapped[str | None] = mapped_column(String)

    experience: Mapped[str | None] = mapped_column(String)

    salary_range: Mapped[str | None] = mapped_column(String)

    job_description: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    skills = relationship(
        "JobSkill",
        back_populates="job"
    )

class JobSkill(Base):
    __tablename__ = "job_skills"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )

    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id")
    )

    skill: Mapped[str] = mapped_column(String)

    job = relationship(
        "Job",
        back_populates="skills"
    )


class JobRawPayload(Base):
    __tablename__ = "job_raw_payloads"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )

    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id")
    )

    raw_payload: Mapped[dict] = mapped_column(JSONB)


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4
    )

    name: Mapped[str] = mapped_column(String)

    content_md: Mapped[str] = mapped_column(Text)

    is_master: Mapped[bool] = mapped_column(
        default=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )