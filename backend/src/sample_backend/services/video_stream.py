"""Python-owned local-video decoder, inference, annotation and synchronized frame delivery.

Each /next response is one complete image+metadata packet. The Electron
renderer never decodes or resubmits video frames during monitoring. Full source
FPS is used by the unchanged main1_chn.py WaterDetector (not 8 FPS).
"""
from __future__ import annotations

import base64
import math
import threading
from collections import deque
from pathlib import Path
from uuid import uuid4

import cv2
from pydantic import BaseModel, Field

from .frame_renderer import render_detection_frame
from .water_detection import Calibration, DemoConfig, WaterDetector
from .water_session import CalibrationInput, DetectorSettings, InvalidFrame, SessionExpired

VIDEO_SUFFIXES = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v'}


class VideoOpenInput(BaseModel):
    file_path: str = Field(min_length=1, max_length=4096)
    calibration: CalibrationInput
    start_time_s: float = Field(default=0.0, ge=0.0, le=86400, allow_inf_nan=False)
    detector: DetectorSettings | None = None
    admin_token: str | None = Field(default=None, max_length=128)


class VideoNextInput(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)


class VideoSeekInput(VideoNextInput):
    time_s: float = Field(ge=0.0, le=86400, allow_inf_nan=False)


class PythonVideoStream:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cap: cv2.VideoCapture | None = None
        self._detector: WaterDetector | None = None
        self._id: str | None = None
        self._fps = 0.0
        self._frame_count = 0
        self._next_index = 0
        self._duration = 0.0
        self._width = 0
        self._height = 0
        self._config = DemoConfig()
        self._history: deque[dict] = deque(maxlen=1500)

    def _close(self) -> None:
        if self._cap is not None:
            self._cap.release()
        self._cap = None
        self._detector = None
        self._id = None
        self._history.clear()

    def close(self) -> None:
        with self._lock:
            self._close()

    def _verify(self, sid: str) -> None:
        if sid != self._id or self._cap is None or self._detector is None:
            raise SessionExpired('Python video session expired; reopen the file')

    def open(self, req: VideoOpenInput) -> dict:
        source = Path(req.file_path)
        if source.suffix.lower() not in VIDEO_SUFFIXES or not source.is_file():
            raise InvalidFrame('Cannot open video file or unsupported video format')
        # Do not follow special pipes/devices; only regular files selected by user.
        if not source.is_file():
            raise InvalidFrame('Video source must be a regular file')
        cap = cv2.VideoCapture(str(source))
        if not cap.isOpened():
            raise InvalidFrame('OpenCV cannot decode this video')
        try:
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = float(cap.get(cv2.CAP_PROP_FPS))
            frame_count = max(0, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
            cal = req.calibration
            if ((height, width) != (cal.height, cal.width)
                    or width <= 0 or height <= 0 or width * height > 4_194_304):
                raise InvalidFrame('Video dimensions differ from wafer calibration or are too large')
            if not math.isfinite(fps) or not 1 <= fps <= 240:
                raise InvalidFrame('Unable to determine source video FPS')
            # API route resolves the approved, persistent settings; direct
            # callers without an override use original DemoConfig defaults.
            cfg = DemoConfig(**(req.detector or DetectorSettings()).model_dump())
            detector = WaterDetector((height, width), fps,
                                     Calibration(cal.cx, cal.cy, cal.radius), cfg)
            with self._lock:
                self._close()
                self._cap = cap
                self._detector = detector
                self._id = uuid4().hex
                self._width, self._height = width, height
                self._fps = fps
                self._frame_count = frame_count
                self._duration = frame_count / fps if frame_count else 0.0
                self._config = cfg
                self._seek_capture(req.start_time_s)
                packet = self._next_locked()
                if packet['ended']:
                    raise InvalidFrame('Video contains no decodable frames')
                return self._session_info() | {'frame': packet}
        except Exception:
            with self._lock:
                if self._cap is cap:
                    self._close()
                else:
                    cap.release()
            raise

    def _session_info(self) -> dict:
        return {'session_id': self._id, 'fps': self._fps,
                'width': self._width, 'height': self._height,
                'duration_s': self._duration, 'frame_count': self._frame_count,
                's_water_threshold': self._config.s_water_threshold,
                'sector_threshold': self._config.sector_threshold,
                'sector_count': self._config.sector_count,
                'inner_radius_ratio': self._config.inner_radius_ratio,
                'outer_radius_ratio': self._config.outer_radius_ratio}

    def _seek_capture(self, time_s: float) -> None:
        assert self._cap is not None and self._detector is not None
        index = max(0, int(round(time_s * self._fps)))
        if self._frame_count:
            index = min(index, self._frame_count - 1)
        if not self._cap.set(cv2.CAP_PROP_POS_FRAMES, index) and index != 0:
            raise InvalidFrame('Video decoder does not support seeking')
        self._next_index = index
        # User-requested seek is a new inspection segment; restart exactly
        # as when main1_chn.py constructs a fresh WaterDetector.
        old = self._detector
        self._detector = WaterDetector((self._height, self._width), self._fps,
                                       old.calib, self._config)
        self._history.clear()

    def seek(self, req: VideoSeekInput) -> dict:
        with self._lock:
            self._verify(req.session_id)
            self._seek_capture(req.time_s)
            return self._next_locked()

    def next(self, req: VideoNextInput) -> dict:
        with self._lock:
            self._verify(req.session_id)
            return self._next_locked()

    def _next_locked(self) -> dict:
        assert self._cap is not None and self._detector is not None
        ok, frame = self._cap.read()
        if not ok:
            return {'ended': True}
        index = self._next_index
        self._next_index += 1
        t = index / self._fps
        # CRITICAL: perform inference on ORIGINAL OpenCV decoded BGR frame.
        # Never JPEG/PNG encode/decode before this call.
        data = self._detector.process(frame)
        annotated = render_detection_frame(frame, self._detector, data)
        ok_jpeg, encoded = cv2.imencode('.jpg', annotated,
                                        [cv2.IMWRITE_JPEG_QUALITY, 84])
        if not ok_jpeg:
            raise InvalidFrame('Cannot encode annotated preview')
        self._history.append({'time_s': t, 's_water': float(data['s_water'])})
        while self._history and self._history[0]['time_s'] < t - 5.0:
            self._history.popleft()
        return {
            'ended': False, 'frame_index': index, 'time_s': t,
            'jpeg_base64': base64.b64encode(encoded).decode('ascii'),
            'result': {
                'session_id': self._id,
                'frame_index': index,
                'status': data['status'],
                's_water': float(data['s_water']),
                'history_ready': bool(data['history_ready']),
                's_water_threshold': self._config.s_water_threshold,
                'sector_threshold': self._config.sector_threshold,
                'sector_count': self._config.sector_count,
                'inner_radius_ratio': self._config.inner_radius_ratio,
                'outer_radius_ratio': self._config.outer_radius_ratio,
                'max_sector_idx': int(data['max_sector_idx']),
                'max_sector_score': float(data['max_sector_score']),
                'sector_scores': [float(v) for v in data['sector_scores']],
                'abnormal_run_s': float(data['abnormal_run_s']),
                'time_s': t, 'history': list(self._history),
            },
        }
