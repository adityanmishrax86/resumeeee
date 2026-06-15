-- Migration 0006: base tables (jobs, resumes, job_skills, job_raw_payloads, resume_match).
-- Earlier migrations (0001-0005) reference these tables but never created them.
-- All statements are IF NOT EXISTS so this is safe to run on existing databases.

CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY,
    source TEXT NOT NULL,
    company_name TEXT,
    role_title TEXT,
    experience TEXT,
    salary_range TEXT,
    job_description TEXT,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS job_skills (
    id UUID PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES jobs(id),
    skill TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_job_skills_job_id ON job_skills(job_id);

CREATE TABLE IF NOT EXISTS job_raw_payloads (
    id UUID PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES jobs(id),
    raw_payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_job_raw_payloads_job_id ON job_raw_payloads(job_id);

CREATE TABLE IF NOT EXISTS resumes (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    content_md TEXT NOT NULL,
    is_master BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP DEFAULT now()
);

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
