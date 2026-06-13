from sqlalchemy import String, DateTime, ForeignKey, Integer, Text
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


class InterviewResearch(Base):
    __tablename__ = "interview_research"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    job_analysis_id: Mapped[str] = mapped_column(ForeignKey("job_analysis.id"))

    result: Mapped[dict] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ResumeMatch(Base):
    __tablename__ = "resume_match"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    resume_id: Mapped[str] = mapped_column(ForeignKey("resumes.id"))

    job_analysis_id: Mapped[str] = mapped_column(ForeignKey("job_analysis.id"))

    result: Mapped[dict] = mapped_column(JSONB)

    overall_score: Mapped[int | None] = mapped_column(Integer, default=None)

    match_summary: Mapped[str | None] = mapped_column(Text, default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ResumeAnalysis(Base):
    __tablename__ = "resume_analysis"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    resume_id: Mapped[str] = mapped_column(ForeignKey("resumes.id"))

    result: Mapped[dict] = mapped_column(JSONB)

    analyzer_version: Mapped[str | None] = mapped_column(String, default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class GapAnalysis(Base):
    __tablename__ = "gap_analyses"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    job_analysis_id: Mapped[str] = mapped_column(ForeignKey("job_analysis.id"))

    resume_match_id: Mapped[str] = mapped_column(ForeignKey("resume_match.id"))

    result: Mapped[dict] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ResumeRewrite(Base):
    __tablename__ = "resume_rewrites"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    resume_id: Mapped[str] = mapped_column(ForeignKey("resumes.id"))

    gap_analysis_id: Mapped[str | None] = mapped_column(ForeignKey("gap_analyses.id"), default=None)

    job_analysis_id: Mapped[str | None] = mapped_column(ForeignKey("job_analysis.id"), default=None)

    result: Mapped[dict] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
