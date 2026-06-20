-- Migration: create application_runs table

CREATE TABLE IF NOT EXISTS application_runs (
    id UUID PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES jobs(id),
    resume_id UUID NOT NULL REFERENCES resumes(id),

    -- queued | running | complete | failed
    status TEXT NOT NULL DEFAULT 'queued',
    error_code TEXT,
    error_detail TEXT,

    -- { "<agent>": { "status": "...", "error_code": "...", "updated_at": "..." }, ... }
    -- agents: job_analyzer | resume_analyzer | resume_matcher | gap_analysis | resume_rewrite | interview_research | cover_letter
    agent_statuses JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_application_runs_job_resume ON application_runs(job_id, resume_id);
CREATE INDEX IF NOT EXISTS ix_application_runs_status ON application_runs(status);
