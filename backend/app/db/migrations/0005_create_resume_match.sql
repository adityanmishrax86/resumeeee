-- Migration: create resume_match table

CREATE TABLE IF NOT EXISTS resume_match (
    id UUID PRIMARY KEY,
    resume_id UUID NOT NULL REFERENCES resumes(id),
    job_analysis_id UUID NOT NULL REFERENCES job_analysis(id),
    result JSONB NOT NULL,
    overall_score INTEGER,
    match_summary TEXT,
    created_at TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_resume_match_resume_id ON resume_match(resume_id);
CREATE INDEX IF NOT EXISTS ix_resume_match_job_analysis_id ON resume_match(job_analysis_id);
