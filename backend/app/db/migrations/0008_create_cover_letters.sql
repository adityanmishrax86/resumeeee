-- Migration 0008: cover_letters — stores 3-variant cover-letter generations.

CREATE TABLE IF NOT EXISTS cover_letters (
    id UUID PRIMARY KEY,
    resume_id UUID NOT NULL REFERENCES resumes(id),
    job_analysis_id UUID REFERENCES job_analysis(id),
    gap_analysis_id UUID REFERENCES gap_analyses(id),
    result JSONB NOT NULL,
    custom_instructions TEXT,
    created_at TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_cover_letters_resume_id ON cover_letters(resume_id);
CREATE INDEX IF NOT EXISTS ix_cover_letters_job_analysis_id ON cover_letters(job_analysis_id);
