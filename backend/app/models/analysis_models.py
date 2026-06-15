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


class ApplicationRun(Base):
    """Per-(job, resume) orchestration run state.

    Drives the new `failed` path in the status endpoint and the single-agent
    retry endpoint. `agent_statuses` is a JSON map keyed by agent name with
    `{status, error_code, updated_at}` so the UI can show which step failed.
    """

    __tablename__ = "application_runs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"))
    resume_id: Mapped[str] = mapped_column(ForeignKey("resumes.id"))

    status: Mapped[str] = mapped_column(String, default="queued")
    error_code: Mapped[str | None] = mapped_column(String, default=None)
    error_detail: Mapped[str | None] = mapped_column(Text, default=None)

    agent_statuses: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CoverLetter(Base):
    __tablename__ = "cover_letters"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    resume_id: Mapped[str] = mapped_column(ForeignKey("resumes.id"))
    job_analysis_id: Mapped[str | None] = mapped_column(ForeignKey("job_analysis.id"), default=None)
    gap_analysis_id: Mapped[str | None] = mapped_column(ForeignKey("gap_analyses.id"), default=None)

    result: Mapped[dict] = mapped_column(JSONB)
    custom_instructions: Mapped[str | None] = mapped_column(Text, default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
