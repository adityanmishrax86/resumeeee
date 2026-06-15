from typing import Optional, List, Type, Any
import os
import re

from app.llm.clients import BaseLLMClient
from app.llm.exceptions import (
    LLMError,
    LLMServiceUnavailable,
    LLMRateLimited,
    LLMTimeout,
    classify_provider_error,
)

try:
    from pydantic_ai import Agent
    # provider/model helpers are optional; import if available
    from pydantic_ai.providers.google import GoogleProvider
    from pydantic_ai.models.google import GoogleModel
except Exception:
    Agent = None
    GoogleProvider = None
    GoogleModel = None


_STATUS_CODE_RE = re.compile(r"status[_ ]?code[=:\s]*(\d{3})", re.IGNORECASE)


def _extract_status_code(exc: Exception) -> Optional[int]:
    """Best-effort pull of an HTTP status code from a pydantic-ai/httpx error.

    pydantic-ai surfaces Google errors with ``status_code`` as both an attribute
    and inside the stringified message (``status_code: 503, ...``). httpx
    exceptions expose ``.response.status_code``. We try the structured paths
    first, then fall back to a regex on the message.
    """
    for attr in ("status_code", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    if response is not None:
        value = getattr(response, "status_code", None)
        if isinstance(value, int):
            return value
    match = _STATUS_CODE_RE.search(str(exc))
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


class GoogleClient(BaseLLMClient):
    """Client for Google Agent using `pydantic_ai.Agent`.

    Expects `GOOGLE_API_KEY` to be present in environment or passed at init.
    This class exposes `generate(system_prompt, user_prompt) -> str` to match
    the `BaseLLMClient` interface used elsewhere in the codebase.

    Args:
        model: Google model name (defaults to GOOGLE_LLM_MODEL env var).
        tools: Optional list of pydantic-ai tools (e.g. duckduckgo_search_tool(),
               web_fetch_tool()). When supplied the Agent runs an agentic
               search-and-fetch loop before producing output.
        output_type: Optional Pydantic model class. When set, pydantic-ai
                     returns a typed instance; generate() serialises it to JSON
                     so the rest of the codebase can parse it normally.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        tools: Optional[List[Any]] = None,
        output_type: Optional[Type[Any]] = None,
    ):
        self.api_key = os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY is not set in environment")

        self.model = model or os.getenv("GOOGLE_LLM_MODEL", "gemini-2.5-flash-preview")
        self.tools = tools or []
        self.output_type = output_type
        self.agent = None

    def _init_agent(self):
        if self.agent is not None:
            return

        if Agent is None:
            raise RuntimeError("pydantic_ai is not installed. Add pydantic-ai to your requirements.")

        agent_kwargs: dict[str, Any] = {}
        if self.tools:
            agent_kwargs["tools"] = self.tools
        if self.output_type is not None:
            agent_kwargs["output_type"] = self.output_type

        try:
            # Prefer an explicit provider + model if the helper classes are available
            if GoogleProvider is not None and GoogleModel is not None:
                provider = GoogleProvider(api_key=self.api_key)
                model_obj = GoogleModel(self.model, provider=provider)
                self.agent = Agent(model_obj, **agent_kwargs)
            else:
                # Fallback: pass model identifier string
                self.agent = Agent(f"google:{self.model}", **agent_kwargs)
        except Exception as exc:
            raise RuntimeError("Failed to initialize pydantic_ai Agent for Google") from exc

    async def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        """Generate a response string using the configured pydantic_ai Agent.

        Async so callers can await it directly inside the FastAPI event loop —
        no asyncio.run() wrapper, no risk of 'Event loop is closed' errors.

        Returns the textual output (or JSON string if the agent produced structured output).
        """
        import asyncio
        import logging as _logging

        self._init_agent()

        prompt = f"{system_prompt}\n\n{user_prompt}" if system_prompt else user_prompt

        try:
            result = await asyncio.wait_for(self.agent.run(prompt), timeout=120.0)
        except asyncio.TimeoutError as exc:
            _logging.getLogger(__name__).error(
                "Google LLM call timed out after 120s for model %s", self.model
            )
            raise LLMTimeout(
                f"LLM response timed out after 120s (model={self.model})",
                provider="google",
                model=self.model,
            ) from exc
        except LLMError:
            raise
        except Exception as exc:
            status_code = _extract_status_code(exc)
            typed = classify_provider_error(exc, provider="google", model=self.model, status_code=status_code)
            _logging.getLogger(__name__).error(
                "Google API call failed: type=%s status=%s model=%s err=%s",
                type(typed).__name__, typed.status_code, self.model, exc,
            )
            raise typed from exc

        # Unwrap result objects that expose `.output` per pydantic-ai docs
        output = getattr(result, "output", result)

        # If the output is a Pydantic model, return its JSON representation
        try:
            if hasattr(output, "model_dump_json"):
                return output.model_dump_json()
            if hasattr(output, "model_dump"):
                import json

                return json.dumps(output.model_dump())
            if hasattr(output, "dict"):
                import json

                return json.dumps(output.dict())
        except Exception:
            # Ignore and fallback to string conversion
            pass

        return str(output)