import logging
import os
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.agents.agent_adapter import AgentAdapter
from app.llm.clients import BaseLLMClient
from app.services.interview_research_service import InterviewResearchService
from app.schemas.interview_research_schema import InterviewResearchResult

logger = logging.getLogger(__name__)


class InterviewResearchAgent(AgentAdapter):
    """Agent wrapper for the InterviewResearchService.

    Routing logic (checked at run-time from LLM_PROVIDER env var):
      - LLM_PROVIDER=google  → builds a GoogleClient with duckduckgo_search_tool()
                                and web_fetch_tool() injected.  The pydantic-ai Agent
                                runs an autonomous search-and-fetch loop and returns a
                                typed InterviewResearchResult; GoogleClient.generate()
                                serialises it to JSON so the service path is unchanged.
      - Any other provider   → uses the BaseLLMClient passed at construction
                                (mock / nvidia / etc.) with manual JSON extraction.
    """

    def __init__(self, llm_client: BaseLLMClient):
        super().__init__(llm_client)
        self._provider = os.getenv("LLM_PROVIDER", "mock").lower()

    async def run(
        self,
        db: Session,
        job_analysis_id: str,
        company_name: Optional[str] = None,
        role_title: Optional[str] = None,
    ) -> InterviewResearchResult:
        if self._provider == "google":
            return await self._run_with_google_tools(db, job_analysis_id, company_name, role_title)
        return await self._run_with_llm_client(db, job_analysis_id, company_name, role_title)

    # ── Google path: pydantic-ai tools baked into GoogleClient ────────────────

    async def _run_with_google_tools(
        self,
        db: Session,
        job_analysis_id: str,
        company_name: Optional[str],
        role_title: Optional[str],
    ) -> InterviewResearchResult:
        """Create a tool-enabled GoogleClient and reuse the standard service path."""
        try:
            from pydantic_ai.common_tools.duckduckgo import duckduckgo_search_tool
            from pydantic_ai.common_tools.web_fetch import web_fetch_tool
        except ImportError as exc:
            raise RuntimeError(
                "pydantic-ai tool extras are not installed. "
                "Run: pip install 'pydantic-ai-slim[duckduckgo,web-fetch]'"
            ) from exc

        from app.llm.google_client import GoogleClient

        tool_client = GoogleClient(
            tools=[duckduckgo_search_tool(), web_fetch_tool()],
            output_type=InterviewResearchResult,
        )

        logger.info(
            "InterviewResearchAgent: google-tools path model=%s job_analysis_id=%s",
            tool_client.model, job_analysis_id,
        )

        # Reuse the standard LLM-client path — GoogleClient.generate() serialises
        # the typed InterviewResearchResult output back to JSON automatically.
        return await self._run_with_llm_client(
            db, job_analysis_id, company_name, role_title, override_client=tool_client
        )

    # ── Standard path: any BaseLLMClient (mock / nvidia / google plain) ───────

    async def _run_with_llm_client(
        self,
        db: Session,
        job_analysis_id: str,
        company_name: Optional[str],
        role_title: Optional[str],
        override_client: Optional[BaseLLMClient] = None,
    ) -> InterviewResearchResult:
        client = override_client or self.llm_client
        system_prompt, user_prompt = InterviewResearchService.prepare_prompts(
            db, job_analysis_id, company_name, role_title
        )

        # Use AgentAdapter._generate() so sync/async is handled automatically,
        # but only when using the injected client (not the Google tool client
        # which is sync-only and not wrapped in AgentAdapter).
        if override_client is not None:
            import asyncio
            response_text = await asyncio.to_thread(
                client.generate,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        else:
            response_text = await self._generate(
                system_prompt=system_prompt, user_prompt=user_prompt
            )

        class _ReplayLLMClient(BaseLLMClient):
            def __init__(self, text: str):
                self._text = text

            def generate(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> str:
                return self._text

        replay = _ReplayLLMClient(response_text)

        return InterviewResearchService.research_interview(
            db=db,
            job_analysis_id=job_analysis_id,
            company_name=company_name,
            role_title=role_title,
            llm_client=replay,
        )

