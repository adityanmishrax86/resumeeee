from app.models.models import Resume
from app.models.analysis_models import JobAnalysis
from app.schemas.resume_schema import ResumeMatchResult
from pathlib import Path
from sqlalchemy.orm import Session
import json
import re
import ast
import logging

class ResumeService:

    @staticmethod
    def create_resume(
        db,
        name: str,
        content: str,
        is_master: bool,
    ) -> str:

        if is_master:

            db.query(Resume).update(
                {"is_master": False}
            )

        resume = Resume(
            name=name,
            content_md=content,
            is_master=is_master
        )

        db.add(resume)

        db.commit()

        db.refresh(resume)

        return str(resume.id)
    
    @staticmethod
    def match_resume(db: Session, response_text) -> ResumeMatchResult:
        """Parse an LLM response (string/dict) into a ResumeMatchResult.

        The LLM output may be a raw JSON string, a JSON inside a code fence, or
        a Python literal. This method tries common strategies to extract and
        parse the JSON, sanitize missing fields with sensible defaults, and
        return a validated `ResumeMatchResult` instance.
        """

        def parse_to_dict(text: str) -> dict | None:
            text = text.strip()

            # Try raw JSON
            try:
                return json.loads(text)
            except Exception:
                pass

            # JSON inside code fence
            m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(1))
                except Exception:
                    pass

            # First {...} block
            m2 = re.search(r"(\{.*\})", text, flags=re.DOTALL)
            if m2:
                block = m2.group(1)
                try:
                    return json.loads(block)
                except Exception:
                    try:
                        return ast.literal_eval(block)
                    except Exception:
                        pass

            # Not parseable
            return None

        # If it's already a ResumeMatchResult, return directly
        if isinstance(response_text, ResumeMatchResult):
            return response_text

        # If it's already a dict, try to build model directly
        if isinstance(response_text, dict):
            raw = response_text
        elif isinstance(response_text, str):
            parsed = parse_to_dict(response_text)
            if parsed is None:
                # treat the entire text as a summary when parsing fails
                raw = {"match_summary": response_text}
            else:
                raw = parsed
        else:
            raise ValueError(f"Unsupported LLM response type: {type(response_text)}")

        # Normalize and supply defaults for missing keys
        def ensure_list(v):
            if v is None:
                return []
            if isinstance(v, list):
                return v
            return [v]

        sanitized = {
            "overall_score": int(raw.get("overall_score") or 0),
            "skills_match_score": int(raw.get("skills_match_score") or 0),
            "experience_match_score": int(raw.get("experience_match_score") or 0),
            "matched_required_skills": ensure_list(raw.get("matched_required_skills")),
            "missing_required_skills": ensure_list(raw.get("missing_required_skills")),
            "matched_preferred_skills": ensure_list(raw.get("matched_preferred_skills")),
            "missing_preferred_skills": ensure_list(raw.get("missing_preferred_skills")),
            "experience_fit": raw.get("experience_fit") or "match",
            "ats_keyword_coverage": ensure_list(raw.get("ats_keyword_coverage")),
            "ats_keyword_gaps": ensure_list(raw.get("ats_keyword_gaps")),
            "strengths": ensure_list(raw.get("strengths")),
            "improvement_suggestions": ensure_list(raw.get("improvement_suggestions")),
            "match_summary": raw.get("match_summary") or raw.get("summary") or "",
        }

        try:
            return ResumeMatchResult(**sanitized)
        except Exception as e:
            logging.exception("Failed to validate ResumeMatchResult: %s", e)
            raise ValueError("Parsed LLM response doesn't conform to ResumeMatchResult schema: %s" % e)
      


    @staticmethod
    def prepare_prompts(db: Session, resume_id: str, job_analysis_id: str)-> tuple[str, str]:

        resume = db.query(Resume).filter(Resume.id == resume_id).first()
        job_analysis = db.query(JobAnalysis).filter(JobAnalysis.id == job_analysis_id).first()

        if not resume or not job_analysis:
            raise ValueError("Resume or Job analysis not found")
        
        resume_content = resume.content_md
        job_analysis_result = job_analysis.result

        base_dir = Path(__file__).resolve().parent.parent
        system_prompt_path = base_dir / "prompts" / "resume_matcher" / "system_prompt.txt"
        user_template_path = base_dir / "prompts" / "resume_matcher" / "user_prompt_template.txt"

        
        if system_prompt_path.exists():
            system_prompt = system_prompt_path.read_text(encoding="utf-8")
        else:
            raise ValueError("Unable to fetch System Prompt for Resume Matcher")

        if user_template_path.exists():
            user_template = user_template_path.read_text(encoding="utf-8")
            try:
                # Format the template with both resume and job analysis data
                user_prompt = user_template.format(
                    resume_Data=resume_content,
                    job_analysis_data=job_analysis_result,
                )
            except Exception:
                logging.exception("Failed formatting user prompt for resume matcher")
                raise ValueError("Couldn't form User Prompt for Resume Matcher")
        else:
            raise ValueError("Unable to form User Prompt. Hence stopping")

        return system_prompt, user_prompt