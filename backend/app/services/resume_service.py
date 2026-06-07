from app.models.models import Resume


class ResumeService:

    @staticmethod
    def create_resume(
        db,
        name,
        content,
        is_master
    ):

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