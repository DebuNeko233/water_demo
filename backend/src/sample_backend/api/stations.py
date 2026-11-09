"""Device-local stage calibration and reference acquisition endpoints."""
from fastapi import APIRouter, HTTPException, Request

from sample_backend.services.station_position import (
    StageCalibrationInput, StageReferenceInput, StageRemoveReferenceInput,
)
from sample_backend.services.water_session import InvalidFrame

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
