-- Migration: create resume_rewrites table
-- Apply with your migration tooling (Alembic recommended)

CREATE TABLE IF NOT EXISTS resume_rewrites (
    id UUID PRIMARY KEY,
    resume_id UUID NOT NULL REFERENCES resumes(id),
    gap_analysis_id UUID REFERENCES gap_analyses(id),
    job_analysis_id UUID REFERENCES job_analysis(id),
    result JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT now()
);
