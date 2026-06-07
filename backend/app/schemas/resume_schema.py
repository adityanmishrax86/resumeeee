from pydantic import BaseModel


class ResumeCreateRequest(BaseModel):
    name: str
    content: str
    is_master: bool = False


class ResumeCreateResponse(BaseModel):
    resume_id: str
    status: str