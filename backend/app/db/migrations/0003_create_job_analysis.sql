-- Migration: create job_analysis table

CREATE TABLE IF NOT EXISTS job_analysis (
    id UUID PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES jobs(id),
    result JSONB NOT NULL,
    analyzer_version TEXT,
    created_at TIMESTAMP DEFAULT now()
);
