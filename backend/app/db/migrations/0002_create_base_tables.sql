-- Migration: create base tables (jobs, resumes, job_skills, job_raw_payloads)

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
