import asyncio
import json
import logging
import os
import re
from typing import Any, AsyncIterator
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.analysis_models import JobAnalysis, InterviewResearch
from app.models.models import Resume
from app.schemas.interview_research_schema import (
    InterviewQuestion,
    InterviewResearchResult,
)
from app.llm.clients import BaseLLMClient

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> str:
    if not text:
        return ""

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end+1]

    match = re.search(r"(\{[\s\S]*\})", text)
    if match:
        return match.group(1)

    return text


class InterviewResearchService:
    @staticmethod
    def research_interview(db: Session, job_analysis_id: str, company_name: str | None, role_title: str | None, llm_client: BaseLLMClient, analyzer_version: str = "v1", custom_instructions: str | None = None) -> InterviewResearchResult:
        ja = db.query(JobAnalysis).filter(JobAnalysis.id == job_analysis_id).first()
        if not ja:
            raise ValueError(f"JobAnalysis with id {job_analysis_id} not found")

        job_json = ja.result if isinstance(ja.result, dict) else {}

        base_dir = Path(__file__).resolve().parent.parent
        system_prompt_path = base_dir / "prompts" / "interview_researcher" / "system_prompt.txt"
        user_template_path = base_dir / "prompts" / "interview_researcher" / "user_prompt_template.txt"

        if system_prompt_path.exists():
            system_prompt = system_prompt_path.read_text(encoding="utf-8")
        else:
            system_prompt = (
                "You are an expert interview coach. Produce an InterviewResearchResult JSON object with role-specific questions, company snapshot, tech stack, hiring signals, culture notes, red flags, and a prep checklist."
            )

        if user_template_path.exists():
            user_template = user_template_path.read_text(encoding="utf-8")
            try:
                user_prompt = user_template.format(job_analysis=json.dumps(job_json), company_name=company_name or "", role_title=role_title or "")
            except Exception:
                user_prompt = f"job_analysis: {json.dumps(job_json)}\ncompany_name: {company_name}\nrole_title: {role_title}"
        else:
            user_prompt = f"job_analysis: {json.dumps(job_json)}\ncompany_name: {company_name}\nrole_title: {role_title}"

        if custom_instructions:
            user_prompt += f"\n\nADDITIONAL USER INSTRUCTIONS (must be followed):\n{custom_instructions}"

        logger.debug("InterviewResearchService: job_analysis_id=%s company=%s role=%s", job_analysis_id, company_name, role_title)

        try:
            response_text = llm_client.generate(system_prompt=system_prompt, user_prompt=user_prompt)
            logger.debug("InterviewResearchService: raw LLM response (truncated)=%s", str(response_text)[:2000])
        except Exception:
            logger.exception("LLM client failed to generate interview research for job_analysis_id=%s", job_analysis_id)
            raise

        json_text = _extract_json(response_text)

        try:
            data = json.loads(json_text)
        except Exception:
            try:
                data = json.loads(response_text)
            except Exception:
                logger.error("LLM returned invalid JSON for interview research job_analysis_id=%s", job_analysis_id)
                raise ValueError("LLM returned invalid JSON for interview research")

        analysis = InterviewResearchResult.parse_obj(data)

        InterviewResearchService._backfill_empty_sections(analysis, job_json, company_name, role_title)

        InterviewResearchService.persist_result(db=db, job_analysis_id=job_analysis_id, result=analysis)

        return analysis

    @staticmethod
    def _backfill_empty_sections(
        result: "InterviewResearchResult",
        job_json: dict,
        company_name: str | None = None,
        role_title: str | None = None,
    ) -> None:
        """Populate `hiring_signals`, `red_flags`, and `prep_checklist` from the
        JobAnalysis when the LLM left them empty.

        These three fields are always JD-derivable, so emptiness is a presentation
        bug rather than a "no evidence" decision. Mutates `result` in place.
        """
        ja = job_json or {}
        role = role_title or ja.get("role_title") or "this role"
        company = company_name or "the company"
        required = list(ja.get("required_skills") or [])
        preferred = list(ja.get("preferred_skills") or [])
        tools = list(ja.get("tools") or [])
        frameworks = list(ja.get("frameworks") or [])
        responsibilities = list(ja.get("responsibilities") or [])
        seniority = (ja.get("seniority_level") or "").strip()
        experience = (ja.get("experience_required") or "").strip()
        domain = (ja.get("domain") or "").strip()

        if not result.hiring_signals:
            signals: list[str] = []
            if required:
                signals.append(
                    f"Hands-on depth expected in: {', '.join(required[:4])}."
                )
            if seniority:
                signals.append(
                    f"Seniority band '{seniority}' — expect system-design and leadership-flavoured rounds."
                )
            if any("ci/cd" in r.lower() or "mlops" in r.lower() or "pipeline" in r.lower() for r in responsibilities):
                signals.append("Strong MLOps / CI-CD orientation — pipeline integration questions are likely.")
            if any("scalab" in r.lower() or "performance" in r.lower() or "cost" in r.lower() for r in responsibilities):
                signals.append("Cost / scalability called out — expect FinOps-style estimation questions.")
            if domain:
                signals.append(f"Domain focus on {domain} — prepare 1-2 case studies in this area.")
            if preferred:
                signals.append(
                    f"'Nice-to-haves' that often become tiebreakers: {', '.join(preferred[:3])}."
                )
            if not signals:
                signals.append("Role expects practical, demonstrable experience over theoretical answers.")
            result.hiring_signals = signals[:6]

        if not result.red_flags:
            flags: list[str] = []
            tool_count = len(tools) + len(frameworks)
            if tool_count >= 6:
                flags.append(
                    f"JD lists {tool_count}+ tools/frameworks — clarify which 2-3 are actually used day-to-day."
                )
            if seniority and any(k in seniority.lower() for k in ("senior", "lead", "architect", "principal")):
                flags.append(
                    "Senior/Architect title — confirm whether the role is hands-on coding or pure leadership."
                )
            if experience:
                flags.append(
                    f"Experience band '{experience}' — confirm it isn't a downlevel disguised as a senior role."
                )
            flags.append("Salary band not disclosed in the JD — ask early to avoid late-stage mismatch.")
            flags.append(
                f"Clarify reporting structure and on-call expectations for {role} at {company}."
            )
            result.red_flags = flags[:6]

        if not result.prep_checklist:
            checklist: list[str] = []
            top_required = required[:5]
            for skill in top_required:
                checklist.append(f"Prepare a 2-minute story demonstrating hands-on work with {skill}.")
            if frameworks:
                checklist.append(
                    f"Build a small demo project using {' + '.join(frameworks[:2])} you can walk through live."
                )
            if any("ci/cd" in r.lower() or "mlops" in r.lower() for r in responsibilities):
                checklist.append(
                    "Sketch a CI/CD pipeline diagram for the role's domain and rehearse explaining trade-offs."
                )
            if "Python" in (ja.get("programming_languages") or []):
                checklist.append("Warm up with 2-3 medium LeetCode-style Python problems on strings and collections.")
            checklist.extend(
                [
                    f"Research recent product launches and engineering blog posts from {company}.",
                    "Prepare 3 STAR stories: a conflict, a critical bug saved, and a cross-functional win.",
                    "Draft 5 thoughtful questions to ask the interviewer about team, roadmap, and metrics of success.",
                    f"Re-read the JD and map each responsibility to a concrete example from your experience.",
                    "Run a mock interview with a peer covering 1 coding + 1 scenario + 1 behavioural question.",
                    "Prepare a concise 60-second pitch tailored to the role and company.",
                ]
            )
            # Dedupe while preserving order, then cap to a reasonable size.
            seen: set[str] = set()
            deduped: list[str] = []
            for item in checklist:
                if item not in seen:
                    seen.add(item)
                    deduped.append(item)
            result.prep_checklist = deduped[:12]

    @staticmethod
    def persist_result(db: Session, job_analysis_id: str, result: "InterviewResearchResult") -> None:
        """Persist an already-validated InterviewResearchResult to the DB.

        Separated so the pydantic-ai tool agent can reuse it without going
        through the full LLM-generate-then-parse flow.
        """
        entry = InterviewResearch(
            job_analysis_id=job_analysis_id,
            result=result.model_dump(),
        )
        db.add(entry)
        db.commit()

    @staticmethod
    def prepare_prompts(db: Session, job_analysis_id: str, company_name: str | None, role_title: str | None, custom_instructions: str | None = None) -> tuple[str, str]:
        ja = db.query(JobAnalysis).filter(JobAnalysis.id == job_analysis_id).first()
        if not ja:
            raise ValueError(f"JobAnalysis with id {job_analysis_id} not found")

        job_json = ja.result if isinstance(ja.result, dict) else {}

        base_dir = Path(__file__).resolve().parent.parent
        system_prompt_path = base_dir / "prompts" / "interview_researcher" / "system_prompt.txt"
        user_template_path = base_dir / "prompts" / "interview_researcher" / "user_prompt_template.txt"

        if system_prompt_path.exists():
            system_prompt = system_prompt_path.read_text(encoding="utf-8")
        else:
            system_prompt = (
                "You are an expert interview coach. Produce an InterviewResearchResult JSON object with role-specific questions, company snapshot, tech stack, hiring signals, culture notes, red flags, and a prep checklist."
            )

        if user_template_path.exists():
            user_template = user_template_path.read_text(encoding="utf-8")
            try:
                user_prompt = user_template.format(job_analysis=json.dumps(job_json), company_name=company_name or "", role_title=role_title or "")
            except Exception:
                user_prompt = f"job_analysis: {json.dumps(job_json)}\ncompany_name: {company_name}\nrole_title: {role_title}"
        else:
            user_prompt = f"job_analysis: {json.dumps(job_json)}\ncompany_name: {company_name}\nrole_title: {role_title}"

        if custom_instructions:
            user_prompt += f"\n\nADDITIONAL USER INSTRUCTIONS (must be followed):\n{custom_instructions}"

        return system_prompt, user_prompt

    @staticmethod
    async def generate_more_questions(
        db: Session,
        job_analysis_id: str,
        company_name: str | None,
        role_title: str | None,
        count: int,
        llm_client: BaseLLMClient,
        custom_instructions: str | None = None,
    ) -> InterviewResearchResult:
        """Append `count` additional non-overlapping questions to the most
        recent InterviewResearch row for this job_analysis. The persisted row
        is mutated and committed; the full updated result is returned.

        The LLM client's `generate` is awaited if it's a coroutine function and
        otherwise run in a worker thread so this method can live inside an
        async FastAPI route without blocking the event loop."""

        existing_row = (
            db.query(InterviewResearch)
            .filter(InterviewResearch.job_analysis_id == job_analysis_id)
            .order_by(InterviewResearch.created_at.desc())
            .first()
        )
        if existing_row is None:
            raise ValueError(
                f"No existing interview research for job_analysis_id={job_analysis_id}; run the base agent first."
            )

        existing_result = InterviewResearchResult.parse_obj(existing_row.result or {})
        existing_questions_text = "\n".join(
            f"- {q.question} ({q.category})" for q in existing_result.role_specific_questions
        ) or "(none)"

        ja = db.query(JobAnalysis).filter(JobAnalysis.id == job_analysis_id).first()
        job_json = ja.result if (ja and isinstance(ja.result, dict)) else {}

        base_dir = Path(__file__).resolve().parent.parent
        system_prompt_path = base_dir / "prompts" / "interview_researcher" / "system_prompt.txt"
        more_template_path = base_dir / "prompts" / "interview_researcher" / "more_user_prompt_template.txt"

        system_prompt = (
            system_prompt_path.read_text(encoding="utf-8")
            if system_prompt_path.exists()
            else "Produce additional InterviewQuestion objects in JSON."
        )

        if more_template_path.exists():
            template = more_template_path.read_text(encoding="utf-8")
            try:
                user_prompt = template.format(
                    existing_questions=existing_questions_text,
                    job_analysis=json.dumps(job_json),
                    company_name=company_name or "",
                    role_title=role_title or "",
                    custom_instructions=custom_instructions or "",
                    count=count,
                )
            except Exception:
                user_prompt = (
                    f"existing_questions:\n{existing_questions_text}\n\n"
                    f"job_analysis: {json.dumps(job_json)}\n"
                    f"company_name: {company_name}\nrole_title: {role_title}\n"
                    f"Generate {count} more InterviewQuestion objects in JSON under role_specific_questions."
                )
        else:
            user_prompt = (
                f"existing_questions:\n{existing_questions_text}\n\n"
                f"job_analysis: {json.dumps(job_json)}\n"
                f"company_name: {company_name}\nrole_title: {role_title}\n"
                f"Generate {count} more InterviewQuestion objects in JSON under role_specific_questions."
            )

        gen = getattr(llm_client, "generate", None)
        if gen is None:
            raise RuntimeError("LLM client has no generate() method")
        if asyncio.iscoroutinefunction(gen):
            response_text = await gen(system_prompt=system_prompt, user_prompt=user_prompt)
        else:
            response_text = await asyncio.to_thread(gen, system_prompt, user_prompt)

        if not isinstance(response_text, str):
            raise RuntimeError(
                f"LLM client returned {type(response_text).__name__}, expected str"
            )

        json_text = _extract_json(response_text)
        try:
            data = json.loads(json_text)
        except Exception:
            logger.warning(
                "generate_more_questions: invalid JSON from LLM (truncated)=%s",
                response_text[:1500],
            )
            try:
                data = json.loads(response_text)
            except Exception:
                raise ValueError("LLM returned invalid JSON for additional questions")

        new_questions = data.get("role_specific_questions", [])
        if not new_questions:
            raise ValueError("LLM returned no additional questions")

        # Append, dedupe by question text, persist.
        existing_qs = {q.question.strip().lower() for q in existing_result.role_specific_questions}
        appended: list = []
        for raw in new_questions:
            try:
                q = InterviewQuestion.parse_obj(raw)
            except Exception:
                continue
            if q.question.strip().lower() in existing_qs:
                continue
            existing_qs.add(q.question.strip().lower())
            appended.append(q)

        if not appended:
            raise ValueError("All returned questions duplicated existing ones")

        existing_result.role_specific_questions.extend(appended)
        existing_row.result = existing_result.model_dump()
        db.add(existing_row)
        db.commit()
        return existing_result

    # ── Streaming detailed answer ────────────────────────────────────────────

    @staticmethod
    async def stream_detailed_answer(
        db: Session,
        job_analysis_id: str | None,
        question: str,
        category: str | None = None,
        why_asked: str | None = None,
        existing_tips: list[str] | None = None,
        custom_instructions: str | None = None,
    ) -> AsyncIterator[str]:
        """Yield text chunks of a detailed answer for a single interview question.

        Provider routing mirrors InterviewResearchAgent:
          - LLM_PROVIDER=google → google.genai streaming
          - LLM_PROVIDER=nvidia → NvidiaNIMClient SSE
          - anything else → mock token stream
        """
        job_json: dict = {}
        if job_analysis_id:
            ja = db.query(JobAnalysis).filter(JobAnalysis.id == job_analysis_id).first()
            if ja is not None and isinstance(ja.result, dict):
                job_json = ja.result

        base_dir = Path(__file__).resolve().parent.parent
        tmpl_path = base_dir / "prompts" / "interview_researcher" / "answer_user_prompt_template.txt"
        if tmpl_path.exists():
            template = tmpl_path.read_text(encoding="utf-8")
        else:
            template = (
                "Question: {question}\nCategory: {category}\nWhy asked: {why_asked}\n"
                "Tips: {existing_tips}\nJob: {job_analysis}\nExtra: {custom_instructions}\n"
                "Write a 200-450 word detailed answer."
            )

        try:
            user_prompt = template.format(
                question=question,
                category=category or "general",
                why_asked=why_asked or "(unspecified)",
                existing_tips="\n".join(f"- {t}" for t in (existing_tips or [])) or "(none)",
                job_analysis=json.dumps(job_json) if job_json else "(no job context)",
                custom_instructions=custom_instructions or "(none)",
            )
        except Exception:
            user_prompt = (
                f"Question: {question}\nCategory: {category}\nWhy asked: {why_asked}\n"
                "Write a 200-450 word detailed answer."
            )

        system_prompt = (
            "You are an expert interview coach. Stream a detailed, ready-to-deliver "
            "answer to the candidate's interview question. Reply with plain prose / markdown "
            "only — no JSON wrapping, no preamble."
        )

        provider = os.getenv("LLM_PROVIDER", "mock").lower()
        if provider == "google":
            async for chunk in InterviewResearchService._stream_google(system_prompt, user_prompt):
                yield chunk
        elif provider == "nvidia":
            async for chunk in InterviewResearchService._stream_nvidia(system_prompt, user_prompt):
                yield chunk
        else:
            async for chunk in InterviewResearchService._stream_mock(question):
                yield chunk

    @staticmethod
    async def _stream_google(system_prompt: str, user_prompt: str) -> AsyncIterator[str]:
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY is not set")

        model = os.getenv("GOOGLE_LLM_MODEL", "gemini-2.5-flash-preview")

        try:
            from google import genai
            from google.genai import types as genai_types
        except Exception as exc:
            raise RuntimeError(
                "google-genai package not installed; cannot stream from Google"
            ) from exc

        client = genai.Client(api_key=api_key)

        def _iter_stream():
            return client.models.generate_content_stream(
                model=model,
                contents=user_prompt,
                config=genai_types.GenerateContentConfig(
                    system_instruction=system_prompt,
                ),
            )

        # google-genai's stream iterator is sync; run it in a worker thread and
        # bridge into an async generator one chunk at a time.
        loop = asyncio.get_event_loop()
        stream = await loop.run_in_executor(None, _iter_stream)
        it = iter(stream)

        def _next():
            try:
                return next(it)
            except StopIteration:
                return None

        while True:
            chunk = await loop.run_in_executor(None, _next)
            if chunk is None:
                break
            text = getattr(chunk, "text", None) or ""
            if text:
                yield text

    @staticmethod
    async def _stream_nvidia(system_prompt: str, user_prompt: str) -> AsyncIterator[str]:
        from app.llm.clients import NvidiaNIMClient

        client = NvidiaNIMClient()
        loop = asyncio.get_event_loop()

        def _start():
            return client.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                stream=True,
            )

        gen = await loop.run_in_executor(None, _start)
        it = iter(gen)

        def _next():
            try:
                return next(it)
            except StopIteration:
                return None

        while True:
            raw = await loop.run_in_executor(None, _next)
            if raw is None or raw == "[DONE]":
                break
            # NIM streams JSON chunks in the OpenAI delta shape.
            try:
                payload = json.loads(raw)
                choices = payload.get("choices") or []
                if choices:
                    delta = choices[0].get("delta") or {}
                    text = delta.get("content") or ""
                    if text:
                        yield text
            except Exception:
                # If it's not JSON, treat as raw text fallback.
                if raw:
                    yield raw

    @staticmethod
    async def _stream_mock(question: str) -> AsyncIterator[str]:
        canned = (
            f"Here is a detailed answer for: **{question}**\n\n"
            "I would approach this by first clarifying the requirement, "
            "then walking through the design tradeoffs, and finally describing "
            "a concrete example from my own work. For instance, when I tackled "
            "a similar problem, I measured the baseline first, identified the "
            "true bottleneck via profiling, and shipped a focused fix that "
            "reduced latency by roughly 35% without rewriting the surrounding "
            "system. Key takeaways: measure before optimising, isolate the "
            "smallest reproducer, and verify with the same metric you started "
            "from."
        )
        for token in canned.split():
            yield token + " "
            await asyncio.sleep(0.01)

    # ── Profile-based questions (resume-grounded) ────────────────────────────

    @staticmethod
    async def generate_profile_questions(
        db: Session,
        resume_id: str,
        job_analysis_id: str | None,
        count: int,
        llm_client: BaseLLMClient,
        company_name: str | None = None,
        role_title: str | None = None,
        custom_instructions: str | None = None,
    ) -> list[InterviewQuestion]:
        """Generate `count` resume-grounded questions. Not persisted.

        Returns a list of InterviewQuestion objects, each tagged with
        ``source="profile"``. The caller decides whether to persist them via
        ``save_user_items``.
        """
        resume = db.query(Resume).filter(Resume.id == resume_id).first()
        if resume is None:
            raise ValueError(f"Resume with id {resume_id} not found")

        resume_content = resume.content_md or ""
        if not resume_content.strip():
            raise ValueError("Resume content is empty; cannot generate profile questions")

        job_json: dict = {}
        if job_analysis_id:
            ja = db.query(JobAnalysis).filter(JobAnalysis.id == job_analysis_id).first()
            if ja is not None and isinstance(ja.result, dict):
                job_json = ja.result

        base_dir = Path(__file__).resolve().parent.parent
        system_prompt_path = base_dir / "prompts" / "interview_researcher" / "system_prompt.txt"
        profile_template_path = base_dir / "prompts" / "interview_researcher" / "profile_user_prompt_template.txt"

        system_prompt = (
            system_prompt_path.read_text(encoding="utf-8")
            if system_prompt_path.exists()
            else "Produce interview questions in JSON."
        )

        if profile_template_path.exists():
            template = profile_template_path.read_text(encoding="utf-8")
            try:
                user_prompt = template.format(
                    resume_content=resume_content,
                    job_analysis=json.dumps(job_json) if job_json else "(none)",
                    company_name=company_name or "",
                    role_title=role_title or "",
                    custom_instructions=custom_instructions or "(none)",
                    count=count,
                )
            except Exception:
                user_prompt = (
                    f"Resume:\n{resume_content}\n\n"
                    f"Job: {json.dumps(job_json)}\n"
                    f"Generate {count} resume-grounded questions as JSON under 'questions'."
                )
        else:
            user_prompt = (
                f"Resume:\n{resume_content}\n\n"
                f"Job: {json.dumps(job_json)}\n"
                f"Generate {count} resume-grounded questions as JSON under 'questions'."
            )

        gen = getattr(llm_client, "generate", None)
        if gen is None:
            raise RuntimeError("LLM client has no generate() method")
        if asyncio.iscoroutinefunction(gen):
            response_text = await gen(system_prompt=system_prompt, user_prompt=user_prompt)
        else:
            response_text = await asyncio.to_thread(gen, system_prompt, user_prompt)

        if not isinstance(response_text, str):
            raise RuntimeError(
                f"LLM client returned {type(response_text).__name__}, expected str"
            )

        json_text = _extract_json(response_text)
        try:
            data = json.loads(json_text)
        except Exception:
            try:
                data = json.loads(response_text)
            except Exception:
                logger.warning(
                    "generate_profile_questions: invalid JSON (truncated)=%s",
                    response_text[:1500],
                )
                raise ValueError("LLM returned invalid JSON for profile questions")

        raw_questions = data.get("questions") or data.get("role_specific_questions") or []
        if not raw_questions:
            raise ValueError("LLM returned no profile questions")

        out: list[InterviewQuestion] = []
        for raw in raw_questions:
            try:
                q = InterviewQuestion.parse_obj(raw)
                q.source = "profile"
                out.append(q)
            except Exception:
                continue

        if not out:
            raise ValueError("All returned profile questions failed validation")

        return out

    # ── Opt-in save (user questions + detailed answers) ──────────────────────

    @staticmethod
    def save_user_items(
        db: Session,
        job_analysis_id: str,
        user_questions: list[dict] | None = None,
        updated_answers: list[dict] | None = None,
    ) -> InterviewResearchResult:
        """Persist user-added questions and/or detailed answers to the latest
        InterviewResearch row for ``job_analysis_id``.

        ``user_questions``: list of dicts matching ``InterviewQuestion`` shape;
        each is prepended to ``role_specific_questions`` (deduped by question
        text) and tagged ``source=<provided>`` defaulting to ``"user"``.

        ``updated_answers``: list of ``{"question": str, "detailed_answer": str}``
        items; for each, the matching question (by trimmed/lowered text) gets
        its ``detailed_answer`` field populated.

        Returns the full updated ``InterviewResearchResult``.
        """
        existing_row = (
            db.query(InterviewResearch)
            .filter(InterviewResearch.job_analysis_id == job_analysis_id)
            .order_by(InterviewResearch.created_at.desc())
            .first()
        )
        if existing_row is None:
            raise ValueError(
                f"No existing interview research for job_analysis_id={job_analysis_id}; "
                "run the base agent first."
            )

        existing_result = InterviewResearchResult.parse_obj(existing_row.result or {})
        existing_text_to_idx: dict[str, int] = {
            q.question.strip().lower(): idx
            for idx, q in enumerate(existing_result.role_specific_questions)
        }

        # Prepend user questions, dedupe by text.
        to_prepend: list[InterviewQuestion] = []
        for raw in user_questions or []:
            try:
                q = InterviewQuestion.parse_obj(raw)
            except Exception:
                continue
            key = q.question.strip().lower()
            if not key or key in existing_text_to_idx:
                continue
            if not q.source:
                q.source = "user"
            to_prepend.append(q)
            existing_text_to_idx[key] = -1  # mark as seen

        if to_prepend:
            existing_result.role_specific_questions = (
                to_prepend + existing_result.role_specific_questions
            )
            # Rebuild index after prepending.
            existing_text_to_idx = {
                q.question.strip().lower(): idx
                for idx, q in enumerate(existing_result.role_specific_questions)
            }

        # Apply detailed_answer updates.
        for raw in updated_answers or []:
            qtext = (raw.get("question") or "").strip().lower()
            answer = raw.get("detailed_answer")
            if not qtext or not answer:
                continue
            idx = existing_text_to_idx.get(qtext)
            if idx is None or idx < 0:
                continue
            existing_result.role_specific_questions[idx].detailed_answer = answer

        existing_row.result = existing_result.model_dump()
        db.add(existing_row)
        db.commit()
        return existing_result
