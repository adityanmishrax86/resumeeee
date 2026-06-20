-- Migration: create interview_research table

CREATE TABLE IF NOT EXISTS interview_research (
    id UUID PRIMARY KEY,
    job_analysis_id UUID NOT NULL REFERENCES job_analysis(id),
    result JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT now()
);
