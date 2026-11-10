"""Python-owned local-video decoding and synchronized annotated frames."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
import base64
import cv2

from sample_backend.services.water_session import InvalidFrame, SessionExpired
from sample_backend.services.user_access import AccessDenied
from sample_backend.services.video_stream import VideoOpenInput, VideoNextInput, VideoSeekInput
from sample_backend.services.video_source import VideoSourceSettings

router = APIRouter(prefix='/api/video')


@router.post('/open')
def video_open(req: VideoOpenInput, request: Request) -> dict:
    try:
        settings = request.app.state.user_access.resolve_detector(req.detector, req.admin_token)
        source = request.app.state.video_source.current()
        return request.app.state.video_stream.open(req.model_copy(update={'detector': settings}), source)
    except AccessDenied as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
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


class VideoSourceAdminInput(BaseModel):
    admin_token: str = Field(min_length=1, max_length=128)


class SaveVideoSourceInput(VideoSourceAdminInput):
    source: VideoSourceSettings


@router.get('/source')
def public_video_source(request: Request) -> dict:
    return request.app.state.video_source.public()


@router.post('/source/config')
def admin_video_source(req: VideoSourceAdminInput, request: Request) -> dict:
    try:
        request.app.state.user_access.require_admin(req.admin_token)
        return request.app.state.video_source.current().model_dump()
    except AccessDenied as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc


@router.post('/source/save')
def save_video_source(req: SaveVideoSourceInput, request: Request) -> dict:
    try:
        request.app.state.user_access.require_admin(req.admin_token)
        result = request.app.state.video_source.save(req.source)
        request.app.state.video_stream.close()
        return {'source': result.model_dump()}
    except AccessDenied as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail='视频源配置保存失败') from exc


@router.post('/snapshot')
def camera_snapshot(req: VideoSourceAdminInput, request: Request) -> dict:
    try:
        request.app.state.user_access.require_admin(req.admin_token)
        source = request.app.state.video_source.current()
        frame = request.app.state.video_stream.snapshot_raw(source)
        height, width = frame.shape[:2]
        if width * height > 4_194_304 or width < 1 or height < 1:
            raise InvalidFrame('摄像头分辨率超过支持范围')
        ok, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not ok:
            raise InvalidFrame('摄像头画面编码失败')
        return {'width': width, 'height': height,
                'jpeg_base64': base64.b64encode(encoded).decode('ascii')}
    except AccessDenied as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
    except (InvalidFrame, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
