from fastapi import FastAPI

from app.api.jobs import router as jobs_router
from app.api.resumes import router as resumes_router

app = FastAPI(
    title="AI Job Copilot"
)

app.include_router(jobs_router)
app.include_router(resumes_router)