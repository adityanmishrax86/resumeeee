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

        # Models occasionally stop short of the requested count even when the
        # response is otherwise valid. Give them one focused repair pass before
        # rejecting the entire interview-prep result.
        if len(analysis.role_specific_questions) != 25:
            repair_prompt = (
                f"{user_prompt}\n\n"
                "CORRECTIVE RETRY: Your previous response contained "
                f"{len(analysis.role_specific_questions)} of the required 25 questions. "
                "Return a complete InterviewResearchResult JSON object with exactly 25 "
                "distinct questions. Preserve the useful existing content and add enough "
                "new, non-duplicate questions grounded in the job description to reach 25. "
                "Keep exactly 3 distinct strong_answer_tips per question and meet all "
                "category minimums. Here is the previous result to repair:\n"
                f"{analysis.model_dump_json()}"
            )
            try:
                repaired_text = llm_client.generate(
                    system_prompt=system_prompt,
                    user_prompt=repair_prompt,
                )
                repaired_data = json.loads(_extract_json(repaired_text))
                repaired_analysis = InterviewResearchResult.model_validate(repaired_data)
                if len(repaired_analysis.role_specific_questions) == 25:
                    analysis = repaired_analysis
                else:
                    logger.warning(
                        "Interview research corrective retry still returned %d questions; "
                        "keeping original response for validation",
                        len(repaired_analysis.role_specific_questions),
                    )
            except Exception:
                logger.exception(
                    "Interview research corrective retry failed for job_analysis_id=%s",
                    job_analysis_id,
                )

        InterviewResearchService._backfill_empty_sections(analysis, job_json, company_name, role_title)
        InterviewResearchService._validate_generated_result(analysis)

        InterviewResearchService.persist_result(db=db, job_analysis_id=job_analysis_id, result=analysis)

        return analysis

    @staticmethod
    def _validate_generated_result(result: InterviewResearchResult) -> None:
        """Enforce the research-agent contract before saving its base result."""
        questions = result.role_specific_questions
        if len(questions) != 25:
            raise ValueError(f"Interview research must contain exactly 25 questions; received {len(questions)}")
        normalized_questions = [re.sub(r"\W+", " ", question.question.lower()).strip() for question in questions]
        if len(set(normalized_questions)) != len(normalized_questions):
            raise ValueError("Interview research contains duplicate or near-duplicate questions")
        if any(len(question.strong_answer_tips) != 3 for question in questions):
            raise ValueError("Every generated interview question must contain exactly 3 answer tips")
        allowed_categories = {"coding", "scenario", "analytical", "behavioural", "technical"}
        if any(question.category not in allowed_categories for question in questions):
            raise ValueError("Interview questions contain an unsupported category")
        if any(len(set(question.strong_answer_tips)) != 3 for question in questions):
            raise ValueError("Interview answer tips must be distinct within each question")
        for category in ("scenario", "analytical", "behavioural", "technical"):
            count = sum(question.category == category for question in questions)
            if count < 4:
                raise ValueError(f"Interview research requires at least 4 {category} questions; received {count}")
        for field_name, values, minimum in (
            ("hiring_signals", result.hiring_signals, 5),
            ("red_flags", result.red_flags, 4),
            ("prep_checklist", result.prep_checklist, 10),
        ):
            if len(values) < minimum:
                raise ValueError(f"Interview research requires at least {minimum} {field_name}; received {len(values)}")

    @staticmethod
    def _backfill_empty_sections(
        result: "InterviewResearchResult",
        job_json: dict,
        company_name: str | None = None,
        role_title: str | None = None,
    ) -> None:
        """Backfill thin `hiring_signals`, `red_flags`, and `prep_checklist`
        from the JobAnalysis when the LLM left them empty or too short.

        These three fields are always JD-derivable, so emptiness is a presentation
        bug rather than a "no evidence" decision. Mutates `result` in place.
        """
        ja = job_json or {}
        for field_name in ("hiring_signals", "red_flags", "prep_checklist"):
            values = getattr(result, field_name)
            seen: set[str] = set()
            unique_values: list[str] = []
            for item in values:
                key = item.strip().lower()
                if key and key not in seen:
                    seen.add(key)
                    unique_values.append(item)
            setattr(result, field_name, unique_values)
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

        signal_fallbacks = [f"The JD explicitly prioritises {skill}." for skill in required]
        signal_fallbacks.extend(
            f"The role includes this stated responsibility: {item}" for item in responsibilities
        )
        if seniority:
            signal_fallbacks.append(f"The JD identifies the level as {seniority}.")
        if domain:
            signal_fallbacks.append(f"The stated domain is {domain}.")
        if tools or frameworks or ja.get("programming_languages"):
            named_stack = tools + frameworks + list(ja.get("programming_languages") or [])
            signal_fallbacks.append(f"The JD names these technologies: {', '.join(named_stack[:5])}.")
        if preferred:
            signal_fallbacks.append(f"The JD lists preferred qualifications: {', '.join(preferred[:4])}.")
        if not experience:
            signal_fallbacks.append("The supplied job analysis does not specify an experience range; clarify level expectations.")
        if not domain:
            signal_fallbacks.append("The supplied job analysis does not identify a domain; clarify the team's core work.")
        if not tools and not frameworks:
            signal_fallbacks.append("The supplied job analysis does not identify a primary toolset; ask about the team's stack.")
        signal_fallbacks.append("Ask how success will be measured against the stated responsibilities.")
        for item in signal_fallbacks:
            if len(result.hiring_signals) >= 5:
                break
            if item not in result.hiring_signals:
                result.hiring_signals.append(item)

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
                    f"Confirm how the stated experience band '{experience}' maps to level and day-to-day scope."
                )
            if not experience:
                flags.append("Ask what experience level and scope the team expects for this role.")
            flags.append(f"Clarify team boundaries and success measures for {role}.")
            flags.append("Ask about compensation range and work-arrangement expectations if they are not covered in the JD.")
            result.red_flags = flags[:6]

        for item in (
            "Ask which listed qualifications are essential on day one and which can be learned after joining.",
            "Clarify the team's boundaries and how this role works with adjacent teams.",
            "Ask what outcomes define success in the first six months.",
            "Confirm whether on-call or out-of-hours support is part of the role.",
            "Ask which tools and responsibilities are most important in the first quarter.",
            "Clarify how the role balances independent delivery with cross-team collaboration.",
        ):
            if len(result.red_flags) >= 4:
                break
            if item not in result.red_flags:
                result.red_flags.append(item)

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
            languages = list(ja.get("programming_languages") or [])
            if languages:
                checklist.append(
                    f"Practise a short role-relevant coding problem in {languages[0]} and explain your trade-offs."
                )
            checklist.extend(
                [
                    f"Research recent product launches and engineering blog posts from {company}.",
                    "Prepare STAR examples from your actual experience that show ownership, problem-solving, and collaboration.",
                    "Draft 5 thoughtful questions to ask the interviewer about team, roadmap, and metrics of success.",
                    f"Re-read the JD and map each responsibility to a concrete example from your experience.",
                    "Run a mock interview with a peer covering one role-specific technical task, one scenario, and one behavioural question.",
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

        checklist_fallbacks = [
            f"Prepare one truthful example from your experience for this stated responsibility: {item}"
            for item in responsibilities
        ]
        checklist_fallbacks.extend(
            f"Review {skill} and prepare to describe your actual hands-on experience."
            for skill in required + preferred
        )
        checklist_fallbacks.extend([
            "Write down the assumptions you would clarify before solving a role-specific scenario.",
            "Prepare questions about the team's workflow, success measures, and technical trade-offs.",
            "Review your resume and be ready to explain the evidence behind each relevant claim.",
            "Choose one relevant technical topic from the JD and practise explaining it without jargon.",
            "Prepare a concise introduction that connects your actual experience to this role.",
            "Select a real project and rehearse explaining its goal, your contribution, and outcome.",
            "Review each required skill and identify the strongest truthful example you can discuss.",
            "Prepare one question about how the team measures success in this role.",
            "Practise explaining a technical trade-off relevant to the listed tools or responsibilities.",
            "Identify any requirement without resume evidence and prepare an honest response.",
        ])
        for item in checklist_fallbacks:
            if len(result.prep_checklist) >= 10:
                break
            if item not in result.prep_checklist:
                result.prep_checklist.append(item)

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
        if len(new_questions) != count:
            raise ValueError(f"Expected exactly {count} additional questions, received {len(new_questions)}")

        # Append, dedupe by question text, persist.
        existing_qs = {q.question.strip().lower() for q in existing_result.role_specific_questions}
        appended: list = []
        for raw in new_questions:
            try:
                q = InterviewQuestion.parse_obj(raw)
            except Exception:
                raise ValueError("An additional interview question did not match the schema")
            if len(q.strong_answer_tips) != 3 or len(set(q.strong_answer_tips)) != 3:
                raise ValueError("Each additional question must include exactly 3 distinct answer tips")
            if q.category not in {"coding", "scenario", "analytical", "behavioural", "technical"}:
                raise ValueError("An additional interview question has an unsupported category")
            if q.question.strip().lower() in existing_qs:
                raise ValueError("An additional question duplicates an existing question")
            existing_qs.add(q.question.strip().lower())
            appended.append(q)

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
          - LLM_PROVIDER=google  → google.genai streaming
          - LLM_PROVIDER=openai  → OpenAI streaming (AsyncOpenAI)
          - LLM_PROVIDER=groq    → Groq streaming (AsyncGroq)
          - anything else        → mock token stream
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
        elif provider == "openai":
            async for chunk in InterviewResearchService._stream_openai(system_prompt, user_prompt):
                yield chunk
        elif provider == "groq":
            async for chunk in InterviewResearchService._stream_groq(system_prompt, user_prompt):
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
    async def _stream_openai(system_prompt: str, user_prompt: str) -> AsyncIterator[str]:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")

        model = os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini")

        try:
            from openai import AsyncOpenAI
        except Exception as exc:
            raise RuntimeError(
                "openai package not installed; cannot stream from OpenAI"
            ) from exc

        client = AsyncOpenAI(api_key=api_key)
        stream = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            stream=True,
        )
        async for chunk in stream:
            text = (chunk.choices[0].delta.content or "") if chunk.choices else ""
            if text:
                yield text

    @staticmethod
    async def _stream_groq(system_prompt: str, user_prompt: str) -> AsyncIterator[str]:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set")

        model = os.getenv("GROQ_LLM_MODEL", "llama-3.3-70b-versatile")

        try:
            from groq import AsyncGroq
        except Exception as exc:
            raise RuntimeError(
                "groq package not installed; cannot stream from Groq"
            ) from exc

        client = AsyncGroq(api_key=api_key)
        stream = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            stream=True,
        )
        async for chunk in stream:
            text = (chunk.choices[0].delta.content or "") if chunk.choices else ""
            if text:
                yield text

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
        if len(raw_questions) != count:
            raise ValueError(f"Expected exactly {count} profile questions, received {len(raw_questions)}")

        out: list[InterviewQuestion] = []
        for raw in raw_questions:
            try:
                q = InterviewQuestion.parse_obj(raw)
                if len(q.strong_answer_tips) != 3:
                    raise ValueError("each question requires exactly three answer tips")
                if q.category not in {"behavioural", "scenario", "technical"}:
                    raise ValueError("unsupported profile question category")
                if len(set(q.strong_answer_tips)) != 3:
                    raise ValueError("answer tips must be distinct")
                q.source = "profile"
                if q.evidence_basis == "inferred":
                    q.evidence_basis = "resume"
                out.append(q)
            except Exception:
                continue

        if len(out) != count:
            raise ValueError(
                f"Expected {count} valid profile questions, received {len(out)}; retry with the requested count"
            )

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
            if q.evidence_basis == "inferred":
                q.evidence_basis = "user"
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
