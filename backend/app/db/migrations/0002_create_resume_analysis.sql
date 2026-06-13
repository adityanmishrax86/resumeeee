-- Migration: create resume_analysis table
-- Apply with your migration tooling (Alembic recommended)

CREATE TABLE IF NOT EXISTS resume_analysis (
    id UUID PRIMARY KEY,
    resume_id UUID NOT NULL REFERENCES resumes(id),
    result JSONB NOT NULL,
    analyzer_version TEXT,
    created_at TIMESTAMP DEFAULT now()
);
