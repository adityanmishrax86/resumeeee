"""Settings service.

Stores the LLM provider/model/api_key as a single DB row. The api_key is
encrypted at rest with Fernet (symmetric AES-128-CBC + HMAC). The master key
lives outside the DB at ``backend/app/.secret_key`` so a DB dump alone cannot
recover plaintext credentials.

Settings are applied to ``os.environ`` so existing code paths
(``GoogleClient``, ``NvidiaNIMClient``, ``interview_research_agent``) keep
reading from env without modification.
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from app.models.settings_model import AppSettings

logger = logging.getLogger(__name__)


_SECRET_KEY_PATH = Path(__file__).resolve().parent.parent / ".secret_key"

# Env var names per provider.
_PROVIDER_ENV: dict[str, dict[str, str]] = {
    "google": {"api_key": "GOOGLE_API_KEY", "model": "GOOGLE_LLM_MODEL"},
    "nvidia": {"api_key": "NVIDIA_API_KEY", "model": "NIM_MODEL"},
    "mock": {},
}


# ── Crypto helpers ────────────────────────────────────────────────────────────


def _load_or_create_key() -> bytes:
    if _SECRET_KEY_PATH.exists():
        return _SECRET_KEY_PATH.read_bytes()
    key = Fernet.generate_key()
    _SECRET_KEY_PATH.write_bytes(key)
    try:
        os.chmod(_SECRET_KEY_PATH, 0o600)
    except OSError:
        pass
    logger.info("Generated new settings encryption key at %s", _SECRET_KEY_PATH)
    return key


def _fernet() -> Fernet:
    return Fernet(_load_or_create_key())


def _encrypt(plaintext: str) -> bytes:
    return _fernet().encrypt(plaintext.encode("utf-8"))


def _decrypt(token: bytes) -> Optional[str]:
    try:
        return _fernet().decrypt(token).decode("utf-8")
    except InvalidToken:
        logger.error("Stored api_key failed Fernet decryption — secret key mismatch")
        return None


# ── Public service ────────────────────────────────────────────────────────────


@dataclass
class SettingsView:
    configured: bool
    source: str  # "db" | "env" | "none"
    provider: Optional[str]
    model: Optional[str]
    has_api_key: bool


class SettingsService:
    @staticmethod
    def _row(db: Session) -> Optional[AppSettings]:
        return db.query(AppSettings).filter(AppSettings.id == 1).first()

    @staticmethod
    def _normalize_provider(provider: Optional[str]) -> Optional[str]:
        if not provider:
            return None
        p = provider.lower().strip()
        if p in ("nim", "nvidia-nim"):
            return "nvidia"
        if p in ("google", "nvidia", "mock"):
            return p
        return None

    @classmethod
    def get_view(cls, db: Session) -> SettingsView:
        row = cls._row(db)
        if row and row.provider:
            provider = cls._normalize_provider(row.provider)
            has_key = bool(row.api_key_encrypted)
            configured = bool(provider and row.model and (has_key or provider == "mock"))
            return SettingsView(
                configured=configured,
                source="db",
                provider=provider,
                model=row.model,
                has_api_key=has_key,
            )

        env_provider = cls._normalize_provider(os.getenv("LLM_PROVIDER"))
        if env_provider:
            envs = _PROVIDER_ENV.get(env_provider, {})
            api_key_env = envs.get("api_key")
            model_env = envs.get("model")
            has_key = bool(os.getenv(api_key_env)) if api_key_env else True
            model_val = os.getenv(model_env) if model_env else None
            configured = bool(env_provider and (model_val or env_provider == "mock") and has_key)
            if configured:
                return SettingsView(
                    configured=True,
                    source="env",
                    provider=env_provider,
                    model=model_val,
                    has_api_key=bool(api_key_env and os.getenv(api_key_env)),
                )

        return SettingsView(
            configured=False, source="none", provider=None, model=None, has_api_key=False
        )

    @classmethod
    def save(
        cls,
        db: Session,
        provider: str,
        model: str,
        api_key: Optional[str],
    ) -> SettingsView:
        norm = cls._normalize_provider(provider)
        if norm is None:
            raise ValueError(f"unsupported provider: {provider}")
        if norm != "mock" and not api_key:
            # Require api_key when first saving a real provider.
            existing = cls._row(db)
            if existing is None or not existing.api_key_encrypted:
                raise ValueError("api_key is required for this provider")

        row = cls._row(db)
        if row is None:
            row = AppSettings(id=1)
            db.add(row)

        row.provider = norm
        row.model = model.strip()
        if api_key:
            row.api_key_encrypted = _encrypt(api_key)
        elif norm == "mock":
            row.api_key_encrypted = None

        from datetime import datetime
        row.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(row)

        cls.apply_to_env(db)
        # Bust agent singletons so the new provider/key takes effect immediately.
        try:
            from app import agents as _agents
            _agents.reset_agent_singletons()
        except Exception:
            logger.exception("Failed to reset agent singletons after settings save")

        return cls.get_view(db)

    @classmethod
    def clear(cls, db: Session) -> SettingsView:
        row = cls._row(db)
        if row is not None:
            db.delete(row)
            db.commit()

        # Repopulate env from .env so DELETE behaves like "forget the DB row
        # and fall back to whatever the original .env defined" instead of
        # leaving stale POST values lingering in os.environ.
        try:
            from dotenv import load_dotenv
            from pathlib import Path
            load_dotenv(
                dotenv_path=Path(__file__).resolve().parent.parent / ".env",
                override=True,
            )
        except Exception:
            logger.exception("Failed to reload .env after clearing settings")

        try:
            from app import agents as _agents
            _agents.reset_agent_singletons()
        except Exception:
            pass
        return cls.get_view(db)

    @classmethod
    def apply_to_env(cls, db: Session) -> None:
        """Materialise DB settings into ``os.environ``.

        Called on startup and after each save. Pydantic-ai's Google provider
        reads ``GOOGLE_API_KEY`` from the env, and the NIM client reads
        ``NVIDIA_API_KEY``/``NIM_MODEL`` — so this is what makes the DB
        config visible to the rest of the codebase.
        """
        row = cls._row(db)
        if row is None or not row.provider:
            return
        provider = cls._normalize_provider(row.provider)
        if provider is None:
            return

        os.environ["LLM_PROVIDER"] = provider
        envs = _PROVIDER_ENV.get(provider, {})

        if row.model and envs.get("model"):
            os.environ[envs["model"]] = row.model

        if envs.get("api_key") and row.api_key_encrypted:
            plain = _decrypt(row.api_key_encrypted)
            if plain:
                os.environ[envs["api_key"]] = plain
