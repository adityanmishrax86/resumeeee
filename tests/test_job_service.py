from app.services.job_service import JobService
from app.services.resume_service import ResumeService
from app.models.models import Job, Resume
from app.models.analysis_models import (
    JobAnalysis,
    ResumeMatch,
    GapAnalysis,
    CoverLetter,
)


class _FakeObj:
    def __init__(self, id: str, **kwargs):
        self.id = id
        for k, v in kwargs.items():
            setattr(self, k, v)


class _FakeQuery:
    def __init__(self, results, deleted_list):
        self._results = results
        self._deleted_list = deleted_list

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self._results

    def first(self):
        return self._results[0] if self._results else None

    def delete(self, synchronize_session=False):
        self._deleted_list.append(self)
        return len(self._results)


class _FakeDB:
    def __init__(self):
        self.store = {}
        self.deleted_queries = []
        self.deleted_objs = []
        self.committed = False

    def query(self, model):
        name = getattr(model, "__name__", "")
        results = self.store.get(name, [])
        # We need to construct a new query object so we can inspect what was deleted
        q = _FakeQuery(results, self.deleted_queries)
        q.model_name = name
        return q

    def delete(self, obj):
        self.deleted_objs.append(obj)

    def commit(self):
        self.committed = True


def test_delete_job_deletes_cover_letter():
    db = _FakeDB()
    job = _FakeObj(id="j1")
    ja = _FakeObj(id="ja1", job_id="j1")
    rm = _FakeObj(id="rm1", job_analysis_id="ja1")
    ga = _FakeObj(id="ga1", resume_match_id="rm1")

    db.store["Job"] = [job]
    db.store["JobAnalysis"] = [ja]
    db.store["ResumeMatch"] = [rm]
    db.store["GapAnalysis"] = [ga]

    success = JobService.delete_job(db, "j1")

    assert success is True
    # Ensure CoverLetter delete was called
    cover_letter_deleted = any(q.model_name == "CoverLetter" for q in db.deleted_queries)
    assert cover_letter_deleted is True
    assert db.committed is True
    assert job in db.deleted_objs


def test_delete_resume_deletes_cover_letter():
    db = _FakeDB()
    resume = _FakeObj(id="r1")
    rm = _FakeObj(id="rm1", resume_id="r1")
    ga = _FakeObj(id="ga1", resume_match_id="rm1")

    db.store["Resume"] = [resume]
    db.store["ResumeMatch"] = [rm]
    db.store["GapAnalysis"] = [ga]

    success = ResumeService.delete_resume(db, "r1")

    assert success is True
    # Ensure CoverLetter delete was called
    cover_letter_deleted = any(q.model_name == "CoverLetter" for q in db.deleted_queries)
    assert cover_letter_deleted is True
    assert db.committed is True
    assert resume in db.deleted_objs
