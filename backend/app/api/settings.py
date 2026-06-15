import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.settings_schema import SettingsResponse, SettingsUpdate
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _view_to_response(view) -> SettingsResponse:
    return SettingsResponse(
        configured=view.configured,
        source=view.source,
        provider=view.provider,
        model=view.model,
        has_api_key=view.has_api_key,
    )


@router.get("", response_model=SettingsResponse)
def get_settings(db: Session = Depends(get_db)):
    return _view_to_response(SettingsService.get_view(db))


@router.post("", response_model=SettingsResponse)
def update_settings(payload: SettingsUpdate, db: Session = Depends(get_db)):
    try:
        view = SettingsService.save(
            db,
            provider=payload.provider,
            model=payload.model,
            api_key=payload.api_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _view_to_response(view)


@router.delete("", response_model=SettingsResponse)
def clear_settings(db: Session = Depends(get_db)):
    return _view_to_response(SettingsService.clear(db))
