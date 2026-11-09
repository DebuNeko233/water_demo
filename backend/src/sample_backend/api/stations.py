"""Device-local stage calibration and reference acquisition endpoints."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from sample_backend.services.profile_archive import export_profile_archive, import_profile_archive
from sample_backend.services.user_access import AccessDenied

from sample_backend.services.station_position import (
    StageCalibrationInput, StageReferenceInput, StageRemoveReferenceInput,
)
from sample_backend.services.water_session import InvalidFrame, WaterDetectionSession

router = APIRouter(prefix='/api/stations')


@router.get('/profile')
def profile(request: Request) -> dict:
    return request.app.state.station_profile.snapshot()


@router.post('/calibration')
def save_calibration(req: StageCalibrationInput, request: Request) -> dict:
    try:
        return request.app.state.station_profile.calibrate(req)
    except (InvalidFrame, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post('/reference')
def capture_reference(req: StageReferenceInput, request: Request) -> dict:
    try:
        return request.app.state.station_profile.capture(req)
    except (InvalidFrame, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post('/reference/remove')
def remove_reference(req: StageRemoveReferenceInput, request: Request) -> dict:
    try:
        return request.app.state.station_profile.remove_reference(req)
    except (InvalidFrame, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class ArchivePathInput(BaseModel):
    file_path: str = Field(min_length=1, max_length=4096)
    admin_token: str = Field(min_length=1, max_length=128)


@router.post('/archive/export')
def export_archive(req: ArchivePathInput, request: Request) -> dict:
    try:
        return export_profile_archive(
            request.app.state.station_profile,
            request.app.state.user_access,
            req.admin_token, req.file_path,
        )
    except AccessDenied as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
    except (InvalidFrame, ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post('/archive/import')
def import_archive(req: ArchivePathInput, request: Request) -> dict:
    try:
        result = import_profile_archive(
            request.app.state.station_profile,
            request.app.state.user_access,
            req.admin_token, req.file_path,
        )
        # Any existing detection session uses the previous calibration and
        # must be reopened rather than silently continuing with stale settings.
        request.app.state.video_stream.close()
        request.app.state.water_detector = WaterDetectionSession()
        return result
    except AccessDenied as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
    except (InvalidFrame, ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
