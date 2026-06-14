-- Migration 0009: app_settings — single-row config for LLM provider/model/api key.
-- The api_key_encrypted column stores a Fernet-encrypted secret; the master key
-- lives outside the DB (backend/app/.secret_key) so a DB dump alone cannot
-- recover plaintext credentials.

CREATE TABLE IF NOT EXISTS app_settings (
    id INTEGER PRIMARY KEY DEFAULT 1,
    provider TEXT,
    model TEXT,
    api_key_encrypted BYTEA,
    extra JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMP DEFAULT now(),
    CONSTRAINT app_settings_singleton CHECK (id = 1)
);
