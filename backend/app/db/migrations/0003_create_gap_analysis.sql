-- Migration: create gap_analyses table
-- Apply with your migration tooling (Alembic recommended)

CREATE TABLE IF NOT EXISTS gap_analyses (
    id UUID PRIMARY KEY,
    job_analysis_id UUID NOT NULL REFERENCES job_analysis(id),
    resume_match_id UUID NOT NULL REFERENCES resume_match(id),
    result JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT now()
);
