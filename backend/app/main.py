from fastapi import FastAPI
import logging
import os

from app.api.jobs import router as jobs_router
from app.api.resumes import router as resumes_router

# Configure basic logging from env var LOG_LEVEL (default INFO)
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
numeric_level = getattr(logging, log_level, logging.INFO)
logging.basicConfig(level=numeric_level, format="%(levelname)s:%(name)s:%(message)s")

app = FastAPI(
    title="AI Job Copilot"
)

app.include_router(jobs_router)
app.include_router(resumes_router)