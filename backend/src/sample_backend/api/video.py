"""Python-owned local-video decoding and synchronized annotated frames."""
from fastapi import APIRouter, HTTPException, Request

from sample_backend.services.water_session import InvalidFrame, SessionExpired
from sample_backend.services.video_stream import VideoOpenInput, VideoNextInput, VideoSeekInput

router = APIRouter(prefix='/api/video')


@router.post('/open')
def video_open(req: VideoOpenInput, request: Request) -> dict:
    try:
        return request.app.state.video_stream.open(req)
    except (ValueError, InvalidFrame) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post('/next')
def video_next(req: VideoNextInput, request: Request) -> dict:
    try:
        return request.app.state.video_stream.next(req)
    except SessionExpired as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InvalidFrame as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post('/seek')
def video_seek(req: VideoSeekInput, request: Request) -> dict:
    try:
        return request.app.state.video_stream.seek(req)
    except SessionExpired as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InvalidFrame as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
