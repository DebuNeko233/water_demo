"""Sequential detection over frames decoded from the SAME browser video displayed to the user.

The actual scoring is WaterDetector from the user's main1_chn.py; this service
owns only transport validation, timestamps and bounded chart history.
"""
from __future__ import annotations

import base64
import binascii
import math
import threading
from collections import deque
from uuid import uuid4

import cv2
import numpy as np
from pydantic import BaseModel, Field

from .water_detection import Calibration, DemoConfig, WaterDetector


class CalibrationInput(BaseModel):
    cx: float = Field(ge=-20000, le=20000)
    cy: float = Field(ge=-20000, le=20000)
    radius: float = Field(gt=10, le=20000)
    width: int = Field(ge=1, le=4096)
    height: int = Field(ge=1, le=4096)


class StartInput(BaseModel):
    calibration: CalibrationInput
    # These are *analyzed* frame samples per second, not the video's native FPS.
    sample_fps: float = Field(default=8.0, ge=2, le=20)


class FrameInput(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    time_s: float = Field(ge=0, le=86400)
    jpeg_base64: str = Field(min_length=8, max_length=2_000_000)


class SessionExpired(ValueError):
    pass


class InvalidFrame(ValueError):
    pass


class WaterDetectionSession:
    """One active video/calibration at a time; requests are serialized by a lock."""

    def __init__(self):
        self._lock = threading.RLock()
        self._id: str | None = None
        self._detector: WaterDetector | None = None
        self._width = 0
        self._height = 0
        self._fps = 8.0
        self._last_time: float | None = None
        self._samples: deque[dict] = deque(maxlen=120)
        self._config = DemoConfig()

    def start(self, config: StartInput) -> dict:
        cal = config.calibration
        if cal.width * cal.height > 4_194_304:
            raise ValueError('Video exceeds the real-time detection size limit (4.2 megapixels)')
        with self._lock:
            self._config = DemoConfig()  # Defaults are from the original main1_chn.py.
            detector = WaterDetector(
                (cal.height, cal.width), config.sample_fps,
                Calibration(cal.cx, cal.cy, cal.radius), self._config,
            )
            self._detector = detector
            self._id = uuid4().hex
            self._width, self._height = cal.width, cal.height
            self._fps = config.sample_fps
            self._last_time = None
            self._samples.clear()
            return {
                'session_id': self._id,
                'sample_fps': self._fps,
                's_water_threshold': self._config.s_water_threshold,
                'sector_threshold': self._config.sector_threshold,
                'history_seconds': self._config.history_seconds,
                'sector_count': self._config.sector_count,
            }

    def process(self, packet: FrameInput) -> dict:
        with self._lock:
            detector = self._detector
            if packet.session_id != self._id or detector is None:
                raise SessionExpired('Detection session changed; start a new session')
            if not math.isfinite(packet.time_s):
                raise InvalidFrame('Frame time must be finite')
            try:
                raw = base64.b64decode(packet.jpeg_base64, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise InvalidFrame('Invalid JPEG base64 data') from exc
            encoded = np.frombuffer(raw, dtype=np.uint8)
            image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
            if image is None:
                raise InvalidFrame('Cannot decode JPEG')
            if image.shape[:2] != (self._height, self._width):
                raise InvalidFrame('Frame resolution does not match calibration')
            # Seeking, repeated frames or a long gap must not carry over an old
            # temporal persistence / NG state. The frontend also starts a new
            # session on explicit seek, video switch, or recalibration.
            if self._last_time is not None and (
                packet.time_s <= self._last_time + 1e-5
                or packet.time_s - self._last_time > max(0.45, 4.0 / self._fps)
            ):
                # Original main1_chn.py has no reset() method: recreate it,
                # preserving its calculations and freshly starting persistence.
                detector = WaterDetector(
                    (self._height, self._width), self._fps, detector.calib, self._config,
                )
                self._detector = detector
                self._samples.clear()
            self._last_time = packet.time_s
            result = detector.process(image)
            s_water = float(result['s_water'])
            self._samples.append({'time_s': packet.time_s, 's_water': s_water})
            while self._samples and self._samples[0]['time_s'] < packet.time_s - 5.0:
                self._samples.popleft()
            return {
                'session_id': self._id,
                'status': result['status'],
                's_water': s_water,
                'history_ready': bool(result['history_ready']),
                's_water_threshold': self._config.s_water_threshold,
                'sector_threshold': self._config.sector_threshold,
                'max_sector_idx': int(result['max_sector_idx']),
                'max_sector_score': float(result['max_sector_score']),
                'sector_scores': [float(x) for x in result['sector_scores']],
                'abnormal_run_s': float(result['abnormal_run_s']),
                'time_s': packet.time_s,
                'history': list(self._samples),
            }