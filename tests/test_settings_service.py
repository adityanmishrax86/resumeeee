import os
from unittest import mock
import pytest
from app.services.settings_service import SettingsService, _PROVIDER_ENV
from app.models.settings_model import AppSettings


class _FakeQuery:
    def __init__(self, row):
        self._row = row

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._row


class _FakeDB:
    def __init__(self, row=None):
        self.row = row
        self.added = None
        self.committed = False
        self.refreshed = False

    def query(self, model):
        return _FakeQuery(self.row)

    def add(self, obj):
        self.added = obj
        self.row = obj

    def commit(self):
        self.committed = True

    def refresh(self, obj):
        self.refreshed = True


def test_settings_save_ollama_no_key_required():
    db = _FakeDB()
    # Ollama should not require an API key to save or configure
    view = SettingsService.save(
        db=db,
        provider="ollama",
        model="llama3",
        api_key=None,
        base_url="http://127.0.0.1:11434/v1",
        timeout=120
    )

    assert view.configured is True
    assert view.provider == "ollama"
    assert view.model == "llama3"
    assert view.has_api_key is False
    assert view.extra == {
        "base_url": "http://127.0.0.1:11434/v1",
        "timeout": 120
    }
    assert db.committed is True


def test_settings_apply_to_env_ollama():
    row = AppSettings(
        id=1,
        provider="ollama",
        model="qwen2.5:7b",
        api_key_encrypted=None,
        extra={
            "base_url": "http://localhost:11434/v1",
            "timeout": 180
        }
    )
    db = _FakeDB(row)

    # Clean existing environment variables
    env_keys = ["LLM_PROVIDER", "OLLAMA_LLM_MODEL", "OLLAMA_BASE_URL", "OLLAMA_TIMEOUT", "OLLAMA_API_KEY"]
    for key in env_keys:
        os.environ.pop(key, None)

    SettingsService.apply_to_env(db)

    assert os.environ.get("LLM_PROVIDER") == "ollama"
    assert os.environ.get("OLLAMA_LLM_MODEL") == "qwen2.5:7b"
    assert os.environ.get("OLLAMA_BASE_URL") == "http://localhost:11434/v1"
    assert os.environ.get("OLLAMA_TIMEOUT") == "180"
    assert "OLLAMA_API_KEY" not in os.environ
