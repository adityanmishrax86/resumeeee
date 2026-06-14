import logging
import os
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.agents.agent_adapter import AgentAdapter
from app.llm.clients import BaseLLMClient
from app.services.interview_research_service import InterviewResearchService
from app.schemas.interview_research_schema import InterviewResearchResult

from pydantic_ai import Agent

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
        custom_instructions: Optional[str] = None,
    ) -> InterviewResearchResult:
        if self._provider == "google":
            return await self._run_with_google_tools(db, job_analysis_id, company_name, role_title, custom_instructions)
        return await self._run_with_llm_client(db, job_analysis_id, company_name, role_title, custom_instructions=custom_instructions)

    # ── Google path: pydantic-ai tools baked into GoogleClient ────────────────

    async def _run_with_google_tools(
        self,
        db: Session,
        job_analysis_id: str,
        company_name: Optional[str],
        role_title: Optional[str],
        custom_instructions: Optional[str] = None,
    ) -> InterviewResearchResult:
        """Run searches directly then make a single LLM call for structured output.

        This avoids the multi-turn tool-calling loop which is slow and unreliable
        with some models (e.g. gemma). Instead we:
          1. Run DuckDuckGo searches directly in Python (via anyio thread)
          2. Embed the snippets into the prompt
          3. Make ONE LLM call with structured output
        """
        import asyncio
        import functools
        import anyio.to_thread

        model = os.getenv("GOOGLE_LLM_MODEL", "gemini-2.5-flash-preview")

        logger.info(
            "InterviewResearchAgent: running single-shot Google agent model=%s job_analysis_id=%s",
            model, job_analysis_id,
        )

        # ── 1. Prepare base prompts ────────────────────────────────────────────
        logger.info("InterviewResearchAgent: Preparing prompts from DB...")
        try:
            system_prompt, user_prompt = InterviewResearchService.prepare_prompts(
                db, job_analysis_id, company_name, role_title, custom_instructions
            )
            logger.info("InterviewResearchAgent: Prompts prepared successfully.")
        except Exception:
            logger.exception("InterviewResearchAgent: Failed to prepare prompts")
            raise

        # ── 2. Run DuckDuckGo searches directly ────────────────────────────────
        try:
            from ddgs.ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS  # legacy package name

        company = company_name or ""
        role = role_title or ""
        # Target platforms where real candidates share interview experiences
        queries = [
            f'site:reddit.com "{company}" "{role}" interview questions asked',
            f'site:glassdoor.com "{company}" interview questions',
            f'site:medium.com "{company}" "{role}" interview experience questions',
            f'site:ambitionbox.com "{company}" interview questions "{role}"',
            f'"{company}" "{role}" interview questions reddit glassdoor experience',
            f'site:geeksforgeeks.org "{role}" interview questions',
            f'site:interviewbit.com "{role}" interview questions',
            f'"{company}" interview process hiring experience questions asked candidates',
            f'"{role}" technical behavioural interview questions "{company}" community',
            f'"{company}" culture work environment employee review interview tips',
        ]

        search_snippets: list[str] = []
        ddgs_client = DDGS()
        for query in queries:
            try:
                search_fn = functools.partial(ddgs_client.text, max_results=6)
                results = await anyio.to_thread.run_sync(search_fn, query)
                for r in (results or []):
                    title = r.get("title", "")
                    body = r.get("body", "")
                    href = r.get("href", "")
                    if body:
                        search_snippets.append(f"**{title}** ({href})\n{body}")
                logger.info("InterviewResearchAgent: search OK for query=%r results=%d", query, len(results or []))
            except Exception as exc:
                logger.warning("InterviewResearchAgent: search failed for query=%r: %s", query, exc)

        snippets_text = "\n\n---\n\n".join(search_snippets) if search_snippets else "No search results available."

        enriched_prompt = (
            f"{system_prompt}\n\n"
            f"## Live search results\n\n{snippets_text}\n\n"
            f"## Task\n\n{user_prompt}\n\n"
            "Use the search results above to produce accurate, detailed interview preparation content."
        )

        # ── 3. Single LLM call with structured output ──────────────────────────
        agent = Agent(
            f"google:{model}",
            output_type=InterviewResearchResult,
        )

        try:
            logger.info("InterviewResearchAgent: starting single LLM call...")
            result = await asyncio.wait_for(agent.run(enriched_prompt), timeout=600.0)
            logger.info("InterviewResearchAgent: LLM call completed.")

            if hasattr(result, "output") and isinstance(result.output, InterviewResearchResult):
                research_result = result.output
            else:
                research_result = InterviewResearchResult.model_validate(result.output)

        except asyncio.TimeoutError:
            logger.error("InterviewResearchAgent: LLM call timed out after 120s")
            raise TimeoutError("Interview research LLM call timed out after 120s")
        except Exception:
            logger.exception("InterviewResearchAgent: Failed during LLM call")
            raise

        # Save to DB
        logger.info("InterviewResearchAgent: Saving research results to database...")
        try:
            final_result = InterviewResearchService.research_interview(
                db=db,
                job_analysis_id=job_analysis_id,
                company_name=company_name,
                role_title=role_title,
                # We don't need llm_client since we already have the parsed result, 
                # but the service expects an llm_client to do the extraction.
                # We can create a quick replay client for it.
                llm_client=type("ReplayClient", (), {"generate": lambda *args, **kwargs: research_result.model_dump_json()})()
            )
            logger.info("InterviewResearchAgent: Successfully saved research results.")
            return final_result
        except Exception as exc:
            logger.exception("InterviewResearchAgent: Failed to save results to database")
            raise

    # ── Standard path: any BaseLLMClient (mock / nvidia / google plain) ───────

    async def _run_with_llm_client(
        self,
        db: Session,
        job_analysis_id: str,
        company_name: Optional[str],
        role_title: Optional[str],
        override_client: Optional[BaseLLMClient] = None,
        custom_instructions: Optional[str] = None,
    ) -> InterviewResearchResult:
        client = override_client or self.llm_client
        system_prompt, user_prompt = InterviewResearchService.prepare_prompts(
            db, job_analysis_id, company_name, role_title, custom_instructions
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

