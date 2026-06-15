import asyncio
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from app.llm.clients import BaseLLMClient


class AgentAdapter(ABC):
    """Base adapter for wrapping an LLM client into an async agent.

    Subclasses should implement `async def run(...) -> BaseModel` and
    use `_generate(...)` to call the underlying LLM client.
    """

    def __init__(self, llm_client: BaseLLMClient):
        self.llm_client = llm_client

    @abstractmethod
    async def run(self, *args: Any, **kwargs: Any) -> BaseModel:
        raise NotImplementedError()

    async def _generate(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> str:
        """Call the underlying LLM client and return a string response.

        This helper will await coroutine-based `generate` methods or run
        synchronous ones in a thread so callers can be async.
        """
        gen = getattr(self.llm_client, "generate", None)
        if gen is None:
            raise RuntimeError("LLM client has no generate() method")

        if asyncio.iscoroutinefunction(gen):
            return await gen(system_prompt=system_prompt, user_prompt=user_prompt, **kwargs)

        # Synchronous generate; run in a thread
        try:
            return await asyncio.to_thread(gen, system_prompt, user_prompt, **kwargs)
        except AttributeError:
            # Python <3.9 fallback
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, lambda: gen(system_prompt=system_prompt, user_prompt=user_prompt, **kwargs))
