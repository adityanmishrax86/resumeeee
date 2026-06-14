"""FastAPI entrypoint.

Logfire is configured once here so:
- every request carries a trace
- stdlib `logging` records show up alongside spans (LogfireLoggingHandler)
- httpx, sqlalchemy, and fastapi are auto-instrumented
- Authorization / API-key headers are scrubbed before export
"""

import logging
import os
from logging import StreamHandler

# Ensure outbound HTTP captures redact auth headers BEFORE logfire/httpx init.
os.environ.setdefault(
    "OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SANITIZE_FIELDS",
    "Authorization,X-Api-Key,x-api-key,X-NIM-API-Key",
)

import logfire
from logfire import ScrubbingOptions
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.database import engine
from app.api.jobs import router as jobs_router
from app.api.resumes import router as resumes_router
from app.api.orchestrator import router as orchestrator_router
from app.api.agents import router as agents_router
from app.api.settings import router as settings_router


# ──────────────────────────────────────────────────────────────────────────────
# Logging + observability
# ──────────────────────────────────────────────────────────────────────────────

log_level = os.getenv("LOG_LEVEL", "INFO").upper()
numeric_level = getattr(logging, log_level, logging.INFO)

logfire.configure(
    service_name=os.getenv("OTEL_SERVICE_NAME", "ai-job-copilot-backend"),
    service_version=os.getenv("APP_VERSION", "0.1.0"),
    environment=os.getenv("APP_ENV", "dev"),
    distributed_tracing=False,
    scrubbing=ScrubbingOptions(
        extra_patterns=[
            "google_api_key",
            "x-api-key",
            "nim_api_key",
            "authorization",
        ],
    ),
)

# Bridge stdlib logging → Logfire + keep the console handler for local dev.
logging.basicConfig(
    level=numeric_level,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logfire.LogfireLoggingHandler(), StreamHandler()],
    force=True,
)

# Instrument SQLAlchemy and outbound HTTP. FastAPI is instrumented below
# once the app object exists.
try:
    logfire.instrument_sqlalchemy(engine=engine)
except Exception:  # pragma: no cover - instrumentation should be best-effort
    logging.getLogger(__name__).warning("Logfire SQLAlchemy instrumentation skipped", exc_info=True)

try:
    logfire.instrument_httpx(capture_all=True)
except Exception:
    logging.getLogger(__name__).warning("Logfire httpx instrumentation skipped", exc_info=True)

# pydantic-ai spans (GenAI semantic attributes for model + tokens).
try:
    logfire.instrument_pydantic_ai()
except Exception:
    logging.getLogger(__name__).warning("Logfire pydantic-ai instrumentation skipped", exc_info=True)


# ──────────────────────────────────────────────────────────────────────────────
# App
# ──────────────────────────────────────────────────────────────────────────────

app = FastAPI(title="AI Job Copilot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # local dev only; tighten in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    logfire.instrument_fastapi(app, capture_headers=True)
except Exception:
    logging.getLogger(__name__).warning("Logfire FastAPI instrumentation skipped", exc_info=True)

app.include_router(jobs_router)
app.include_router(resumes_router)
app.include_router(orchestrator_router)
app.include_router(agents_router)
app.include_router(settings_router)


# ──────────────────────────────────────────────────────────────────────────────
# App settings: ensure the table exists and hydrate os.environ from the DB.
# Pydantic-ai / NIM clients read credentials from env, so this is what makes
# frontend-managed settings take effect process-wide.
# ──────────────────────────────────────────────────────────────────────────────

@app.on_event("startup")
def _bootstrap_app_settings() -> None:
    from app.db.database import SessionLocal
    from app.models.settings_model import AppSettings
    from app.services.settings_service import SettingsService

    try:
        AppSettings.__table__.create(bind=engine, checkfirst=True)
    except Exception:
        logging.getLogger(__name__).warning(
            "Could not ensure app_settings table exists", exc_info=True
        )

    db = SessionLocal()
    try:
        SettingsService.apply_to_env(db)
    except Exception:
        logging.getLogger(__name__).warning(
            "Failed to apply DB-stored LLM settings to env", exc_info=True
        )
    finally:
        db.close()
