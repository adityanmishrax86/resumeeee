"""Typed exceptions for LLM provider failures.

The orchestrator distinguishes between fatal (whole-run stop) and retryable
(single-agent retry) failures based on these exception types.
"""

from typing import Optional


class LLMError(RuntimeError):
    """Base class for all LLM provider failures."""

    def __init__(self, message: str, *, status_code: Optional[int] = None, provider: Optional[str] = None, model: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.provider = provider
        self.model = model


class LLMServiceUnavailable(LLMError):
    """503 / model unavailable — orchestrator stops the entire run."""


class LLMRateLimited(LLMError):
    """429 / quota exceeded — orchestrator stops the chain but marks the
    failed agent as retryable so the user can re-run just that agent."""


class LLMTimeout(LLMError):
    """Request exceeded the per-call timeout — treated like rate-limited (retryable)."""


class LLMInvalidResponse(LLMError):
    """Provider returned a response that could not be parsed into the
    expected schema. Retryable at the agent level."""


def classify_provider_error(exc: Exception, *, provider: Optional[str] = None, model: Optional[str] = None, status_code: Optional[int] = None) -> LLMError:
    """Map a raw provider exception to one of the typed LLM errors above.

    Prefers `status_code` when supplied (e.g. from `resp.status_code`).
    Falls back to scanning the stringified exception for known markers.
    """
    if isinstance(exc, LLMError):
        return exc

    msg = str(exc)
    lower = msg.lower()

    code = status_code
    if code is None:
        for token in ("429", "503", "500", "502", "504"):
            if token in msg:
                code = int(token)
                break

    if code == 503 or "unavailable" in lower or "model is overloaded" in lower:
        return LLMServiceUnavailable(msg, status_code=code or 503, provider=provider, model=model)
    if code == 429 or "too many requests" in lower or "quota" in lower or "rate limit" in lower:
        return LLMRateLimited(msg, status_code=code or 429, provider=provider, model=model)
    if code in (500, 502, 504) or "internal server error" in lower or "bad gateway" in lower or "gateway timeout" in lower:
        return LLMServiceUnavailable(msg, status_code=code, provider=provider, model=model)
    return LLMError(msg, status_code=code, provider=provider, model=model)
