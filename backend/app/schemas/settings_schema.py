from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


SettingsSource = Literal["db", "env", "none"]
ProviderName = Literal["google", "openai", "groq", "ollama", "mock"]


class SettingsResponse(BaseModel):
    """Public settings view. Never includes the plaintext api_key."""

    configured: bool
    source: SettingsSource
    provider: Optional[ProviderName] = None
    model: Optional[str] = None
    has_api_key: bool = False
    extra: Dict[str, Any] = Field(default_factory=dict)


class SettingsUpdate(BaseModel):
    provider: ProviderName
    model: str = Field(min_length=1)
    # Optional on update: empty/None means "keep existing key".
    # Required when provider != mock and no key exists yet (enforced by service).
    api_key: Optional[str] = None
    # Ollama base_url (e.g. http://localhost:11434/v1). Stored in the extras JSONB.
    base_url: Optional[str] = None
    # Ollama timeout in seconds. Stored in the extras JSONB.
    timeout: Optional[int] = None
