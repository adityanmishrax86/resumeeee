from typing import Literal, Optional

from pydantic import BaseModel, Field


SettingsSource = Literal["db", "env", "none"]
ProviderName = Literal["google", "openai", "groq", "mock"]


class SettingsResponse(BaseModel):
    """Public settings view. Never includes the plaintext api_key."""

    configured: bool
    source: SettingsSource
    provider: Optional[ProviderName] = None
    model: Optional[str] = None
    has_api_key: bool = False


class SettingsUpdate(BaseModel):
    provider: ProviderName
    model: str = Field(min_length=1)
    # Optional on update: empty/None means "keep existing key".
    # Required when provider != mock and no key exists yet (enforced by service).
    api_key: Optional[str] = None
