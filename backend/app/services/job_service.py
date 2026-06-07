from app.models.models import (
    Job,
    JobSkill,
    JobRawPayload
)


class JobService:

    @staticmethod
    def ingest_job(db, source, payload):

        job = Job(
            source=source,
            company_name=payload.get("companyName"),
            role_title=payload.get("roleTitle"),
            experience=payload.get("experience"),
            salary_range=payload.get("salaryRange"),
            job_description=payload.get("jobDescription")
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