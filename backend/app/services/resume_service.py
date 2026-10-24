from app.models.models import Resume
from app.models.analysis_models import (
    JobAnalysis,
    ResumeAnalysis,
    ResumeMatch,
    GapAnalysis,
    ResumeRewrite,
    ApplicationRun,
    CoverLetter,
)
from app.schemas.resume_schema import ResumeMatchResult
from pathlib import Path
from sqlalchemy.orm import Session
import json
import re
import ast
import logging
import math

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
    def delete_resume(db, resume_id: str) -> bool:
        """Cascade-delete a resume and every derived analysis row.

        Walks from deepest descendant up to the resume itself. Returns True
        if the resume existed and was deleted.
        """
        resume = db.query(Resume).filter(Resume.id == resume_id).first()
        if resume is None:
            return False

        rm_ids = [str(r.id) for r in db.query(ResumeMatch).filter(ResumeMatch.resume_id == resume_id).all()]
        ga_ids = []
        if rm_ids:
            ga_ids = [str(g.id) for g in db.query(GapAnalysis).filter(GapAnalysis.resume_match_id.in_(rm_ids)).all()]

        if ga_ids:
            db.query(ResumeRewrite).filter(ResumeRewrite.gap_analysis_id.in_(ga_ids)).delete(synchronize_session=False)
            db.query(GapAnalysis).filter(GapAnalysis.id.in_(ga_ids)).delete(synchronize_session=False)
        db.query(CoverLetter).filter(CoverLetter.resume_id == resume_id).delete(synchronize_session=False)
        db.query(ResumeRewrite).filter(ResumeRewrite.resume_id == resume_id).delete(synchronize_session=False)
        db.query(ResumeMatch).filter(ResumeMatch.resume_id == resume_id).delete(synchronize_session=False)
        db.query(ResumeAnalysis).filter(ResumeAnalysis.resume_id == resume_id).delete(synchronize_session=False)
        db.query(ApplicationRun).filter(ApplicationRun.resume_id == resume_id).delete(synchronize_session=False)
        db.delete(resume)
        db.commit()
        return True
    
    @staticmethod
    def match_resume(db: Session, response_text, resume_id: str | None = None, job_analysis_id: str | None = None) -> ResumeMatchResult:
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

        # Parse model-authored narrative fields, but derive all match lists and
        # scores from the persisted source documents for consistent results.
        if isinstance(response_text, ResumeMatchResult) or hasattr(response_text, "model_dump"):
            raw = response_text.model_dump()
        # If it's already a dict, try to build model directly
        if isinstance(response_text, dict):
            raw = response_text
        elif isinstance(response_text, str):
            parsed = parse_to_dict(response_text)
            if parsed is None:
                raise ValueError("LLM returned invalid JSON for resume matching")
            else:
                raw = parsed
        elif not (isinstance(response_text, ResumeMatchResult) or hasattr(response_text, "model_dump")):
            raise ValueError(f"Unsupported LLM response type: {type(response_text)}")

        # Normalize and supply defaults for missing keys
        def ensure_list(v):
            if v is None:
                return []
            if isinstance(v, list):
                return v
            return [v]

        if not resume_id or not job_analysis_id:
            # Compatibility for callers that only need schema normalization.
            sanitized = {
                "overall_score": int(raw.get("overall_score") or 0),
                "skills_match_score": int(raw.get("skills_match_score") or 0),
                "experience_match_score": int(raw.get("experience_match_score") or 0),
                "domain_score": int(raw.get("domain_score") or 0),
                "matched_required_skills": ensure_list(raw.get("matched_required_skills")),
                "missing_required_skills": ensure_list(raw.get("missing_required_skills")),
                "matched_preferred_skills": ensure_list(raw.get("matched_preferred_skills")),
                "missing_preferred_skills": ensure_list(raw.get("missing_preferred_skills")),
                "experience_fit": raw.get("experience_fit") or "match",
                "ats_keyword_coverage": ensure_list(raw.get("ats_keyword_coverage")),
                "ats_keyword_gaps": ensure_list(raw.get("ats_keyword_gaps")),
                "skill_evidence": raw.get("skill_evidence") or {},
                "ats_keyword_evidence": raw.get("ats_keyword_evidence") or {},
                "strengths": ensure_list(raw.get("strengths"))[:4],
                "improvement_suggestions": ensure_list(raw.get("improvement_suggestions"))[:5],
                "match_summary": raw.get("match_summary") or raw.get("summary") or "",
            }
        else:
            resume = db.query(Resume).filter(Resume.id == resume_id).first()
            job_row = db.query(JobAnalysis).filter(JobAnalysis.id == job_analysis_id).first()
            if resume is None or job_row is None:
                raise ValueError("Resume or job analysis not found")

            source_text = (resume.content_md or "").lower()
            job_data = job_row.result if isinstance(job_row.result, dict) else {}

            aliases = {
                "js": ("javascript",), "javascript": ("js",),
                "k8s": ("kubernetes",), "kubernetes": ("k8s",),
                "ci/cd": ("continuous integration", "continuous delivery", "continuous integration/continuous delivery"),
                "continuous integration": ("ci/cd",), "continuous delivery": ("ci/cd",),
                "rest api testing": ("api testing",), "api testing": ("rest api testing",),
            }

            def present(phrase: str) -> bool:
                candidates = {phrase.lower().strip()}
                for term in tuple(candidates):
                    candidates.update(aliases.get(term, ()))
                candidates.discard("")
                for candidate in candidates:
                    pattern = r"(?<!\w)" + re.escape(candidate) + r"(?!\w)"
                    if re.search(pattern, source_text, flags=re.IGNORECASE):
                        return True
                return False

            def evidence(phrase: str) -> str:
                candidates = {phrase.lower().strip()}
                for term in tuple(candidates):
                    candidates.update(aliases.get(term, ()))
                candidates.discard("")
                for candidate in candidates:
                    pattern = r"(?<!\w)" + re.escape(candidate) + r"(?!\w)"
                    match = re.search(pattern, resume.content_md or "", flags=re.IGNORECASE)
                    if match:
                        start = max(0, match.start() - 45)
                        end = min(len(resume.content_md or ""), match.end() + 45)
                        return " ".join((resume.content_md or "")[start:end].split())
                return ""

            def partition(field: str) -> tuple[list[str], list[str]]:
                values = [str(x) for x in (job_data.get(field) or []) if str(x).strip()]
                matched = [item for item in values if present(item)]
                missing = [item for item in values if item not in matched]
                return matched, missing

            matched_required, missing_required = partition("required_skills")
            matched_preferred, missing_preferred = partition("preferred_skills")
            ats_coverage, ats_gaps = partition("ats_keywords")
            skills_score = math.floor(100 * len(matched_required) / max(1, len(matched_required) + len(missing_required)) + 0.5)

            from app.models.analysis_models import ResumeAnalysis
            latest_analysis = (
                db.query(ResumeAnalysis)
                .filter(ResumeAnalysis.resume_id == resume_id)
                .order_by(ResumeAnalysis.created_at.desc())
                .first()
            )
            analysis_data = latest_analysis.result if latest_analysis and isinstance(latest_analysis.result, dict) else {}
            candidate_years = (
                int(analysis_data.get("experience_years") or 0)
                if latest_analysis is not None else None
            )
            exp_text = str(job_data.get("experience_required") or "")
            year_values = [int(value) for value in re.findall(r"\d+", exp_text)]
            minimum_years = year_values[0] if year_values else 0
            maximum_years = year_values[1] if len(year_values) > 1 and "+" not in exp_text else None
            shortfall = max(0, minimum_years - candidate_years) if candidate_years is not None else None
            if not minimum_years:
                experience_score = 85
                experience_fit = "match"
            elif candidate_years is None:
                experience_score = 50
                experience_fit = "match"
            elif maximum_years is not None and candidate_years > maximum_years + 5:
                experience_score = 75
                experience_fit = "over_qualified"
            elif shortfall == 0:
                experience_score = 95
                experience_fit = "match"
            elif shortfall == 1:
                experience_score = 72
                experience_fit = "under_qualified"
            elif shortfall <= 2:
                experience_score = 52
                experience_fit = "under_qualified"
            else:
                experience_score = max(0, 60 - 10 * shortfall)
                experience_fit = "under_qualified"

            domain = str(job_data.get("domain") or "").lower().strip()
            resume_domains = [str(item).lower().strip() for item in (analysis_data.get("domains") or [])]
            if not domain:
                domain_score = 70
            elif latest_analysis is None:
                domain_score = 50
            elif any(domain == item for item in resume_domains):
                domain_score = 95
            elif any(set(re.findall(r"[a-z0-9+#]+", domain)) & set(re.findall(r"[a-z0-9+#]+", item)) for item in resume_domains):
                domain_score = 65
            else:
                domain_score = 30

            overall_score = math.floor(skills_score * 0.5 + experience_score * 0.3 + domain_score * 0.2 + 0.5)
            sanitized = {
                "overall_score": overall_score,
                "skills_match_score": skills_score,
                "experience_match_score": experience_score,
                "domain_score": domain_score,
                "matched_required_skills": matched_required,
                "missing_required_skills": missing_required,
                "matched_preferred_skills": matched_preferred,
                "missing_preferred_skills": missing_preferred,
                "experience_fit": experience_fit,
                "ats_keyword_coverage": ats_coverage,
                "ats_keyword_gaps": ats_gaps,
                "skill_evidence": {
                    item: evidence(item)
                    for item in matched_required + matched_preferred
                },
                "ats_keyword_evidence": {
                    item: evidence(item) for item in ats_coverage
                },
                "strengths": ensure_list(raw.get("strengths"))[:4],
                "improvement_suggestions": ensure_list(raw.get("improvement_suggestions"))[:5],
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
                    job_analysis_data=json.dumps(job_analysis_result, ensure_ascii=False),
                )
            except Exception:
                logging.exception("Failed formatting user prompt for resume matcher")
                raise ValueError("Couldn't form User Prompt for Resume Matcher")
        else:
            raise ValueError("Unable to form User Prompt. Hence stopping")

        return system_prompt, user_prompt
