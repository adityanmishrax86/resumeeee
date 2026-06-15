from pydantic import BaseModel, ConfigDict
from typing import Any, Optional
from datetime import datetime
from uuid import UUID


class JobIngestRequest(BaseModel):
    source: str
    payload: dict[str, Any]


class JobIngestResponse(BaseModel):
    job_id: str
    status: str


class JobListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_name: Optional[str] = None
    role_title: Optional[str] = None
    source: str
    created_at: datetime


class JobDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_name: Optional[str] = None
    role_title: Optional[str] = None
    source: str
    experience: Optional[str] = None
    salary_range: Optional[str] = None
    job_description: Optional[str] = None
    created_at: datetime