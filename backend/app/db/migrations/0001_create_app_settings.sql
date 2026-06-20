-- Migration: create app_settings table
-- Single-row config for LLM provider/model/api key.

CREATE TABLE IF NOT EXISTS app_settings (
    id INTEGER PRIMARY KEY DEFAULT 1,
    provider TEXT,
    model TEXT,
    api_key_encrypted BYTEA,
    extra JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMP DEFAULT now(),
    CONSTRAINT app_settings_singleton CHECK (id = 1)
);
