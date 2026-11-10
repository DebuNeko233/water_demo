"""Python-owned local-video decoding and synchronized annotated frames."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
import base64
import math
import cv2

from sample_backend.services.water_session import InvalidFrame, SessionExpired
from sample_backend.services.user_access import AccessDenied
from sample_backend.services.video_stream import (
    VideoOpenInput, VideoNextInput, VideoSeekInput, VideoStopInput,
    VideoDimensionsMismatch, VideoDimensionsTooLarge,
)
from sample_backend.services.video_source import VideoSourceSettings, open_capture

router = APIRouter(prefix='/api/video')


@router.post('/open')
def video_open(req: VideoOpenInput, request: Request) -> dict:
    try:
        settings = request.app.state.user_access.resolve_detector(req.detector, req.admin_token)
        source = request.app.state.video_source.current()
        return request.app.state.video_stream.open(req.model_copy(update={'detector': settings}), source)
    except AccessDenied as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
    except VideoDimensionsMismatch as exc:
        raise HTTPException(status_code=422, detail={
            'code': 'CALIBRATION_RESOLUTION_MISMATCH',
            'video_width': exc.width, 'video_height': exc.height,
            'calibration_width': exc.calibration_width,
            'calibration_height': exc.calibration_height,
        }) from exc
    except VideoDimensionsTooLarge as exc:
        raise HTTPException(status_code=422, detail={
            'code': 'VIDEO_RESOLUTION_TOO_LARGE',
            'video_width': exc.width, 'video_height': exc.height,
        }) from exc
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


@router.post('/detection/start')
def start_detection(req: VideoStopInput, request: Request) -> dict:
    try:
        return request.app.state.video_stream.set_detection(req.session_id, True)
    except SessionExpired as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post('/detection/stop')
def stop_detection(req: VideoStopInput, request: Request) -> dict:
    try:
        return request.app.state.video_stream.set_detection(req.session_id, False)
    except SessionExpired as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post('/stop')
def video_stop(req: VideoStopInput, request: Request) -> dict:
    try:
        request.app.state.video_stream.stop(req.session_id)
        return {'stopped': True}
    except SessionExpired as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


class VideoSourceAdminInput(BaseModel):
    admin_token: str = Field(min_length=1, max_length=128)


class VideoSnapshotInput(VideoSourceAdminInput):
    time_s: float = Field(default=0.0, ge=0.0, le=86400, allow_inf_nan=False)


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
def camera_snapshot(req: VideoSnapshotInput, request: Request) -> dict:
    try:
        request.app.state.user_access.require_admin(req.admin_token)
        source = request.app.state.video_source.current()
        duration_s = 0.0
        time_s = 0.0
        if source.kind == 'file':
            cap = open_capture(source)
            try:
                fps = float(cap.get(cv2.CAP_PROP_FPS))
                frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                if not math.isfinite(fps) or fps <= 0 or frames <= 0:
                    raise InvalidFrame('视频时长或帧率不可读取')
                duration_s = frames / fps
                frame_index = min(frames - 1, max(0, round(req.time_s * fps)))
                if not cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index) and frame_index:
                    raise InvalidFrame('无法定位视频帧')
                ok, frame = cap.read()
                if not ok or frame is None:
                    raise InvalidFrame('所选视频帧不可读取')
                time_s = frame_index / fps
            finally:
                cap.release()
        else:
            frame = request.app.state.video_stream.snapshot_raw(source)
        height, width = frame.shape[:2]
        if width * height > 4_194_304 or width < 1 or height < 1:
            raise InvalidFrame('摄像头分辨率超过支持范围')
        ok, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not ok:
            raise InvalidFrame('摄像头画面编码失败')
        return {'width': width, 'height': height,
                'duration_s': duration_s, 'time_s': time_s,
                'jpeg_base64': base64.b64encode(encoded).decode('ascii')}
    except AccessDenied as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
    except (InvalidFrame, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
