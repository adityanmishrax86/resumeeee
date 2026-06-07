from pydantic import BaseModel
from typing import Any


class JobIngestRequest(BaseModel):
    source: str
    payload: dict[str, Any]


class JobIngestResponse(BaseModel):
    job_id: str
    status: str