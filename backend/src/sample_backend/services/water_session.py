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
from pydantic import BaseModel, Field, model_validator

from .water_detection import Calibration, DemoConfig, WaterDetector


class CalibrationInput(BaseModel):
    cx: float = Field(ge=-20000, le=20000)
    cy: float = Field(ge=-20000, le=20000)
    radius: float = Field(gt=10, le=20000)
    width: int = Field(ge=1, le=4096)
    height: int = Field(ge=1, le=4096)



class DetectorSettings(BaseModel):
    """Editable numeric subset of the original DemoConfig (8 FPS is fixed)."""
    inner_radius_ratio: float = Field(DemoConfig.inner_radius_ratio, ge=0.05, le=1.5, allow_inf_nan=False)
    outer_radius_ratio: float = Field(DemoConfig.outer_radius_ratio, ge=0.05, le=1.5, allow_inf_nan=False)
    diff_threshold: float = Field(DemoConfig.diff_threshold, ge=0.0, le=255.0, allow_inf_nan=False)
    history_seconds: float = Field(DemoConfig.history_seconds, ge=0.125, le=3.0, allow_inf_nan=False)
    persistence_threshold: float = Field(DemoConfig.persistence_threshold, ge=0.0, le=1.0, allow_inf_nan=False)
    s_water_threshold: float = Field(DemoConfig.s_water_threshold, ge=0.0, le=1.0, allow_inf_nan=False)
    # Reference-frame station position classification, NOT water OK/NG.
    station_match_threshold: float = Field(0.78, ge=0.50, le=0.99, allow_inf_nan=False)
    ng_hold_seconds: float = Field(DemoConfig.ng_hold_seconds, ge=0.0, le=30.0, allow_inf_nan=False)
    recover_hold_seconds: float = Field(DemoConfig.recover_hold_seconds, ge=0.0, le=30.0, allow_inf_nan=False)
    sector_count: int = Field(DemoConfig.sector_count, ge=4, le=72)
    sector_threshold: float = Field(DemoConfig.sector_threshold, ge=0.0, le=1.0, allow_inf_nan=False)
    blur_ksize: int = Field(DemoConfig.blur_ksize, ge=0, le=15)

    @model_validator(mode='after')
    def check_geometry_and_blur(self):
        if self.inner_radius_ratio >= self.outer_radius_ratio:
            raise ValueError('inner_radius_ratio must be less than outer_radius_ratio')
        if self.blur_ksize > 1 and self.blur_ksize % 2 == 0:
            raise ValueError('blur_ksize must be 0, 1, or an odd number')
        return self

class StartInput(BaseModel):
    calibration: CalibrationInput
    # These are *analyzed* frame samples per second, not the video's native FPS.
    sample_fps: float = Field(default=8.0, ge=8.0, le=8.0)
    detector: DetectorSettings | None = None
    admin_token: str | None = Field(default=None, max_length=128)


class FrameInput(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    time_s: float = Field(ge=0, le=86400)
    png_base64: str | None = Field(default=None, min_length=8, max_length=24_000_000)
    jpeg_base64: str | None = Field(default=None, min_length=8, max_length=2_000_000)

    @model_validator(mode='after')
    def exactly_one_format(self):
        if (self.png_base64 is None) == (self.jpeg_base64 is None):
            raise ValueError('Supply exactly one of png_base64 or jpeg_base64')
        return self


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
            self._config = DemoConfig(**(config.detector or DetectorSettings()).model_dump(
                exclude={'station_match_threshold'}))
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
                'inner_radius_ratio': self._config.inner_radius_ratio,
                'outer_radius_ratio': self._config.outer_radius_ratio,
            }

    def process(self, packet: FrameInput) -> dict:
        with self._lock:
            detector = self._detector
            if packet.session_id != self._id or detector is None:
                raise SessionExpired('Detection session changed; start a new session')
            if not math.isfinite(packet.time_s):
                raise InvalidFrame('Frame time must be finite')
            try:
                raw = base64.b64decode(packet.png_base64 or packet.jpeg_base64 or '', validate=True)
            except (ValueError, binascii.Error) as exc:
                raise InvalidFrame('Invalid image base64 data') from exc
            if packet.png_base64 is not None and not raw.startswith(b'\x89PNG\r\n\x1a\n'):
                raise InvalidFrame('Expected lossless PNG image')
            if packet.jpeg_base64 is not None and not raw.startswith(b'\xff\xd8'):
                raise InvalidFrame('Expected JPEG image')
            encoded = np.frombuffer(raw, dtype=np.uint8)
            image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
            if image is None:
                raise InvalidFrame('Cannot decode image')
            if image.shape[:2] != (self._height, self._width):
                raise InvalidFrame('Frame resolution does not match calibration')
            # main1_chn.py calls WaterDetector.process(frame) in sequence and
            # NEVER resets on a skipped input frame. Transport must not invent
            # its own history/NG reset. Seek, video change and recalibration
            # explicitly start a new session instead.
            if self._last_time is not None and packet.time_s <= self._last_time:
                raise InvalidFrame('Frame time must increase; start a new session after seeking')
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
                'sector_count': self._config.sector_count,
                'inner_radius_ratio': self._config.inner_radius_ratio,
                'outer_radius_ratio': self._config.outer_radius_ratio,
                'max_sector_idx': int(result['max_sector_idx']),
                'max_sector_score': float(result['max_sector_score']),
                'sector_scores': [float(x) for x in result['sector_scores']],
                'abnormal_run_s': float(result['abnormal_run_s']),
                'time_s': packet.time_s,
                'history': list(self._samples),
            }