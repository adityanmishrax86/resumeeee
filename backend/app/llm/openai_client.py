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
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider
except Exception:
    Agent = None
    OpenAIChatModel = None
    OpenAIProvider = None


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


class OpenAIClient(BaseLLMClient):
    """Client for OpenAI models using ``pydantic_ai.Agent``.

    Expects ``OPENAI_API_KEY`` to be present in the environment or passed at
    init.  Exposes ``async generate(system_prompt, user_prompt) -> str`` to
    match the ``BaseLLMClient`` interface.

    Args:
        model: OpenAI model name (defaults to ``OPENAI_LLM_MODEL`` env var,
               then ``gpt-4o-mini``).
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
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is not set in environment")

        self.model = model or os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini")
        self.tools = tools or []
        self.output_type = output_type
        self.agent = None

    def _init_agent(self):
        if self.agent is not None:
            return

        if Agent is None or OpenAIChatModel is None or OpenAIProvider is None:
            raise RuntimeError(
                "pydantic_ai with openai extras is not installed. "
                "Add 'pydantic-ai' and 'openai' to your requirements."
            )

        agent_kwargs: dict[str, Any] = {}
        if self.tools:
            agent_kwargs["tools"] = self.tools
        if self.output_type is not None:
            agent_kwargs["output_type"] = self.output_type

        try:
            provider = OpenAIProvider(api_key=self.api_key)
            model_obj = OpenAIChatModel(self.model, provider=provider)
            self.agent = Agent(model_obj, **agent_kwargs)
        except Exception as exc:
            raise RuntimeError("Failed to initialize pydantic_ai Agent for OpenAI") from exc

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

        try:
            result = await asyncio.wait_for(self.agent.run(prompt), timeout=120.0)
        except asyncio.TimeoutError as exc:
            _logging.getLogger(__name__).error(
                "OpenAI LLM call timed out after 120s for model %s", self.model
            )
            raise LLMTimeout(
                f"LLM response timed out after 120s (model={self.model})",
                provider="openai",
                model=self.model,
            ) from exc
        except LLMError:
            raise
        except Exception as exc:
            status_code = _extract_status_code(exc)
            typed = classify_provider_error(exc, provider="openai", model=self.model, status_code=status_code)
            _logging.getLogger(__name__).error(
                "OpenAI API call failed: type=%s status=%s model=%s err=%s",
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
