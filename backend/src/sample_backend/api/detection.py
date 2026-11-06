"""Frame-wise detection API using the visible local-video image as its source."""
from fastapi import APIRouter, HTTPException, Request
from sample_backend.services.water_session import (
    FrameInput, InvalidFrame, SessionExpired, StartInput,
)

router = APIRouter(prefix='/api/detection')


@router.post('/start')
def detection_start(body: StartInput, request: Request) -> dict:
    try:
        return request.app.state.water_detector.start(body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post('/frame')
def detection_frame(body: FrameInput, request: Request) -> dict:
    try:
        return request.app.state.water_detector.process(body)
    except SessionExpired as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InvalidFrame as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc