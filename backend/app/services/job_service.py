from app.models.models import (
    Job,
    JobSkill,
    JobRawPayload
)
from app.models.analysis_models import (
    JobAnalysis,
    ResumeMatch,
    GapAnalysis,
    ResumeRewrite,
    InterviewResearch,
    ApplicationRun,
    CoverLetter,
)


class JobService:

    @staticmethod
    def ingest_job(db, source, payload):

        job = Job(
            source=source,
            company_name=payload.get("companyName") or "Unknown Company",
            role_title=payload.get("roleTitle") or "Unknown Role",
            experience=payload.get("experience") or "Unknown",
            salary_range=payload.get("salaryRange") or "Unknown",
            job_description=payload.get("jobDescription") or payload.get("description") or "No description provided"
        )

        db.add(job)
        db.flush()

        raw = JobRawPayload(
            job_id=job.id,
            raw_payload=payload
        )

        db.add(raw)

        skills = payload.get("keySkills", [])

        for skill in skills:

            db.add(
                JobSkill(
                    job_id=job.id,
                    skill=skill
                )
            )

        db.commit()

        return str(job.id)

    @staticmethod
    def delete_job(db, job_id: str) -> bool:
        """Cascade-delete a job and every derived analysis.

        Order matters: children before parents, since the existing schema
        does not declare ON DELETE CASCADE on the FK columns.
        Returns True if the job existed and was deleted.
        """
        job = db.query(Job).filter(Job.id == job_id).first()
        if job is None:
            return False

        # Find all analyses derived from this job up-front so we can walk
        # downstream rows by id without re-querying after deletes.
        ja_ids = [str(j.id) for j in db.query(JobAnalysis).filter(JobAnalysis.job_id == job_id).all()]
        rm_ids = []
        if ja_ids:
            rm_ids = [str(r.id) for r in db.query(ResumeMatch).filter(ResumeMatch.job_analysis_id.in_(ja_ids)).all()]
        ga_ids = []
        if rm_ids:
            ga_ids = [str(g.id) for g in db.query(GapAnalysis).filter(GapAnalysis.resume_match_id.in_(rm_ids)).all()]

        # Deepest descendants first.
        if ga_ids:
            db.query(ResumeRewrite).filter(ResumeRewrite.gap_analysis_id.in_(ga_ids)).delete(synchronize_session=False)
        if ja_ids:
            db.query(CoverLetter).filter(
                (CoverLetter.job_analysis_id.in_(ja_ids)) |
                (CoverLetter.gap_analysis_id.in_(ga_ids) if ga_ids else False)
            ).delete(synchronize_session=False)
            db.query(ResumeRewrite).filter(ResumeRewrite.job_analysis_id.in_(ja_ids)).delete(synchronize_session=False)
            db.query(GapAnalysis).filter(GapAnalysis.job_analysis_id.in_(ja_ids)).delete(synchronize_session=False)
            db.query(ResumeMatch).filter(ResumeMatch.job_analysis_id.in_(ja_ids)).delete(synchronize_session=False)
            db.query(InterviewResearch).filter(InterviewResearch.job_analysis_id.in_(ja_ids)).delete(synchronize_session=False)
            db.query(JobAnalysis).filter(JobAnalysis.id.in_(ja_ids)).delete(synchronize_session=False)

        db.query(ApplicationRun).filter(ApplicationRun.job_id == job_id).delete(synchronize_session=False)
        db.query(JobSkill).filter(JobSkill.job_id == job_id).delete(synchronize_session=False)
        db.query(JobRawPayload).filter(JobRawPayload.job_id == job_id).delete(synchronize_session=False)
        db.delete(job)
        db.commit()
        return True