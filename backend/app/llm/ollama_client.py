from typing import Optional, List, Type, Any
import os
import re

from app.llm.clients import BaseLLMClient
from app.llm.exceptions import (
    LLMError,
    LLMTimeout,
    classify_provider_error,
)

try:
    from pydantic_ai import Agent
    from pydantic_ai.models.ollama import OllamaModel
    from pydantic_ai.providers.ollama import OllamaProvider
except Exception:
    Agent = None
    OllamaModel = None
    OllamaProvider = None


_STATUS_CODE_RE = re.compile(r"status[_ ]?code[=:\s]*(\d{3})", re.IGNORECASE)


def _extract_status_code(exc: Exception) -> Optional[int]:
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


class OllamaClient(BaseLLMClient):
    """Client for Ollama models using ``pydantic_ai.Agent``.

    Connects to a local (or remote) Ollama instance via its OpenAI-compatible
    API.  No API key is required for self-hosted Ollama; set ``OLLAMA_API_KEY``
    only when connecting to Ollama Cloud.

    Env vars:
        OLLAMA_BASE_URL  – Base URL of the Ollama server
                           (default: ``http://localhost:11434/v1``).
        OLLAMA_API_KEY   – Optional API key (needed for Ollama Cloud).
        OLLAMA_LLM_MODEL – Model name to pull/use (default: ``llama3``).

    Args:
        model: Ollama model name (defaults to ``OLLAMA_LLM_MODEL`` env var,
               then ``llama3``).
        tools: Optional list of pydantic-ai tools injected into the Agent.
        output_type: Optional Pydantic model class for structured output;
                     ``generate()`` serialises the result to JSON so the rest
                     of the codebase can parse it normally.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        tools: Optional[List[Any]] = None,
        output_type: Optional[Type[Any]] = None,
    ):
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        self.api_key = os.getenv("OLLAMA_API_KEY")  # Optional; None for local
        self.model = model or os.getenv("OLLAMA_LLM_MODEL", "llama3")
        self.tools = tools or []
        self.output_type = output_type
        self.agent = None

    def _init_agent(self):
        if self.agent is not None:
            return

        if Agent is None or OllamaModel is None or OllamaProvider is None:
            raise RuntimeError(
                "pydantic_ai with ollama extras is not installed. "
                "Add 'pydantic-ai' to your requirements."
            )

        agent_kwargs: dict[str, Any] = {}
        if self.tools:
            agent_kwargs["tools"] = self.tools
        if self.output_type is not None:
            agent_kwargs["output_type"] = self.output_type

        try:
            provider_kwargs: dict[str, Any] = {"base_url": self.base_url}
            if self.api_key:
                provider_kwargs["api_key"] = self.api_key
            provider = OllamaProvider(**provider_kwargs)
            model_obj = OllamaModel(self.model, provider=provider)
            self.agent = Agent(model_obj, **agent_kwargs)
        except Exception as exc:
            raise RuntimeError("Failed to initialize pydantic_ai Agent for Ollama") from exc

    async def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        """Generate a response string using the configured pydantic_ai Agent.

        Async so callers can await it directly inside the FastAPI event loop.
        Returns the textual output (or JSON string for structured output).
        """
        import asyncio
        import json
        import logging as _logging

        self._init_agent()

        prompt = f"{system_prompt}\n\n{user_prompt}" if system_prompt else user_prompt

        # Ollama can be slower than cloud providers; allow a longer timeout.
        timeout = float(os.getenv("OLLAMA_TIMEOUT", "300"))

        try:
            result = await asyncio.wait_for(self.agent.run(prompt), timeout=timeout)
        except asyncio.TimeoutError as exc:
            _logging.getLogger(__name__).error(
                "Ollama LLM call timed out after %.0fs for model %s", timeout, self.model
            )
            raise LLMTimeout(
                f"LLM response timed out after {timeout:.0f}s (model={self.model})",
                provider="ollama",
                model=self.model,
            ) from exc
        except LLMError:
            raise
        except Exception as exc:
            status_code = _extract_status_code(exc)
            typed = classify_provider_error(exc, provider="ollama", model=self.model, status_code=status_code)
            _logging.getLogger(__name__).error(
                "Ollama API call failed: type=%s status=%s model=%s err=%s",
                type(typed).__name__, typed.status_code, self.model, exc,
            )
            raise typed from exc

        output = getattr(result, "output", result)

        if hasattr(output, "model_dump_json"):
            return output.model_dump_json()
        if hasattr(output, "model_dump"):
            return json.dumps(output.model_dump())
        if isinstance(output, str):
            return output
        return json.dumps(output)
