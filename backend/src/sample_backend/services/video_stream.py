"""Python-owned local-video decoder, inference, annotation and synchronized frame delivery.

Each /next response is one complete image+metadata packet. The Electron
renderer never decodes or resubmits video frames during monitoring. Full source
FPS is used by the unchanged main1_chn.py WaterDetector (not 8 FPS).
"""
from __future__ import annotations

import base64
import math
import threading
import time
from collections import deque
from pathlib import Path
from uuid import uuid4

import cv2
from pydantic import BaseModel, Field
from typing import Literal

from .frame_renderer import render_detection_frame, resize_display_frame
from .roi_detector import RoiWaterDetector
from .station_position import STAGES, StageProfileStore, ReferencePositionRecognizer
from .water_detection import Calibration, DemoConfig
from .water_session import CalibrationInput, DetectorSettings, InvalidFrame, SessionExpired
from .video_source import VideoSourceSettings, open_capture

VIDEO_SUFFIXES = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v'}
MAX_FRAME_PIXELS = 4_194_304


class VideoDimensionsMismatch(InvalidFrame):
    """The selected input does not match the ROI's original pixel grid."""

    def __init__(self, width: int, height: int, calibration: CalibrationInput):
        self.width = width
        self.height = height
        self.calibration_width = calibration.width
        self.calibration_height = calibration.height
        super().__init__(
            f'视频 {width}×{height} 与标定 {calibration.width}×{calibration.height} '
            '分辨率不一致，请管理员重新标注')


class VideoDimensionsTooLarge(InvalidFrame):
    """An input exceeds the tested detector memory / frame-size limit."""

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        super().__init__(
            f'视频 {width}×{height} 超过检测分辨率上限，请降低摄像头或视频分辨率')



class VideoOpenInput(BaseModel):
    file_path: str = Field(default='', max_length=4096)
    calibration: CalibrationInput
    start_time_s: float = Field(default=0.0, ge=0.0, le=86400, allow_inf_nan=False)
    detector: DetectorSettings | None = None
    admin_token: str | None = Field(default=None, max_length=128)
    stage_mode: Literal['single', 'auto'] = 'single'
    detecting: bool = True  # Existing direct API clients keep inference on.


class VideoNextInput(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    # File mode: infer every frame, transmit only the final display JPEG.
    # A default of 1 keeps existing clients fully backward compatible.
    batch_frames: int = Field(default=1, ge=1, le=6)


class VideoSeekInput(VideoNextInput):
    time_s: float = Field(ge=0.0, le=86400, allow_inf_nan=False)


class VideoStopInput(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)


class PythonVideoStream:
    def __init__(self, profile: StageProfileStore | None = None) -> None:
        self._profile = profile
        self._lock = threading.RLock()
        self._cap: cv2.VideoCapture | None = None
        self._detector: RoiWaterDetector | None = None
        self._detecting = True
        self._initial_calibration: Calibration | None = None
        self._id: str | None = None
        self._fps = 0.0
        self._frame_count = 0
        self._next_index = 0
        self._duration = 0.0
        self._width = 0
        self._height = 0
        self._config = DemoConfig()
        self._station_match_threshold = 0.78
        self._history: deque[dict] = deque(maxlen=1500)
        self._mode = 'single'
        self._recognizer: ReferencePositionRecognizer | None = None
        self._stage_calibrations: dict[str, dict] = {}
        self._active_stage: str | None = None
        self._candidate_stage: str | None = None
        self._candidate_count = 0
        self._source_kind = 'file'
        self._last_raw_frame = None
        self._probe_frame = None
        self._live_cv = threading.Condition(self._lock)
        self._live_thread: threading.Thread | None = None
        self._live_stop = False
        self._live_packet: dict | None = None
        self._live_overlay_result: dict | None = None
        self._live_serial = 0
        self._live_served = 0
        self._live_error = ''

    def _close(self) -> None:
        self._live_stop = True
        self._live_cv.notify_all()
        self._live_packet = None
        self._live_overlay_result = None
        self._last_raw_frame = None
        self._probe_frame = None
        if self._cap is not None:
            self._cap.release()
        self._cap = None
        self._detector = None
        self._initial_calibration = None
        self._detecting = False
        self._id = None
        self._history.clear()
        self._recognizer = None
        self._stage_calibrations = {}
        self._active_stage = None
        self._candidate_stage = None
        self._candidate_count = 0

    def close(self) -> None:
        with self._lock:
            self._close()

    def stop(self, session_id: str) -> None:
        """Stop only the specified session; stale UI requests cannot stop a new one."""
        with self._lock:
            self._verify(session_id)
            self._close()


    def set_detection(self, session_id: str, enabled: bool) -> dict:
        """Toggle inference without seeking, pausing or closing the source."""
        with self._live_cv:
            self._verify(session_id)
            if enabled and not self._detecting:
                self._history.clear()
                self._candidate_stage = None
                self._candidate_count = 0
                self._active_stage = None
                if self._mode == 'auto':
                    self._detector = None
                else:
                    assert self._initial_calibration is not None
                    self._detector = RoiWaterDetector(
                        (self._height, self._width), self._fps,
                        self._initial_calibration, self._config)
            self._detecting = enabled
            if not enabled:
                self._live_overlay_result = None
                self._history.clear()
            return {'detecting': self._detecting}

    def _verify(self, sid: str) -> None:
        if sid != self._id or self._cap is None:
            raise SessionExpired('Python video session expired; reopen the file')

    def open(self, req: VideoOpenInput, source_settings: VideoSourceSettings | None = None) -> dict:
        settings = source_settings or VideoSourceSettings()
        cap = open_capture(settings, req.file_path)
        live = settings.kind != 'file'
        try:
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            first_frame = None
            if live:
                ok, first_frame = cap.read()
                if not ok or first_frame is None:
                    raise InvalidFrame('摄像头无法读取画面')
                height, width = first_frame.shape[:2]
            fps = float(cap.get(cv2.CAP_PROP_FPS))
            frame_count = max(0, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
            cal = req.calibration
            if width <= 0 or height <= 0:
                raise InvalidFrame('无法读取视频分辨率')
            if width * height > MAX_FRAME_PIXELS:
                raise VideoDimensionsTooLarge(width, height)
            if (height, width) != (cal.height, cal.width):
                raise VideoDimensionsMismatch(width, height, cal)
            if not math.isfinite(fps) or not 1 <= fps <= 240:
                if live:
                    fps = 30.0  # Fallback when the camera driver omits FPS.
                else:
                    raise InvalidFrame('Unable to determine source video FPS')
            # API route resolves the approved, persistent settings; direct
            # callers without an override use original DemoConfig defaults.
            approved = req.detector or DetectorSettings()
            cfg = DemoConfig(**approved.model_dump(exclude={'station_match_threshold'}))
            stage_profile = None
            recognizer = None
            if req.stage_mode == 'auto':
                if self._profile is None:
                    raise InvalidFrame('三工位参考帧配置尚未初始化')
                stage_profile, recognizer = self._profile.build(width, height)
                recognizer.threshold = approved.station_match_threshold
            detector = RoiWaterDetector((height, width), fps,
                                     Calibration(cal.cx, cal.cy, cal.radius), cfg)
            with self._lock:
                self._close()
                self._cap = cap
                self._detector = detector
                self._initial_calibration = Calibration(cal.cx, cal.cy, cal.radius)
                self._detecting = req.detecting
                self._id = uuid4().hex
                self._width, self._height = width, height
                self._fps = fps
                self._frame_count = frame_count
                self._duration = frame_count / fps if frame_count and not live else 0.0
                self._frame_count = frame_count if not live else 0
                self._source_kind = settings.kind
                self._probe_frame = first_frame
                self._live_stop = False
                self._live_error = ''
                self._live_serial = 0
                self._live_served = 0
                self._live_packet = None
                self._live_overlay_result = None
                self._config = cfg
                self._station_match_threshold = approved.station_match_threshold
                self._mode = req.stage_mode
                self._recognizer = recognizer
                self._stage_calibrations = (stage_profile['stages'] if stage_profile else {})
                if not live:
                    self._seek_capture(req.start_time_s)
                else:
                    self._next_index = 0
                    self._history.clear()
                    if self._mode == 'auto':
                        self._detector = None
                packet = self._next_locked()
                if packet['ended']:
                    raise InvalidFrame('视频源无法读取第一帧')
                if live:
                    self._live_packet = packet
                    self._live_serial = 1
                    self._live_served = 1
                    thread = threading.Thread(target=self._live_loop, args=(self._id,),
                                              name='ZeboVision-LiveCapture', daemon=True)
                    self._live_thread = thread
                    thread.start()
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
                'outer_radius_ratio': self._config.outer_radius_ratio,
                'stage_mode': self._mode, 'source_kind': self._source_kind,
                'is_live': self._source_kind != 'file',
                'station_match_threshold': self._station_match_threshold,
                'detecting': self._detecting}

    def _seek_capture(self, time_s: float) -> None:
        if self._source_kind != 'file':
            raise InvalidFrame('实时摄像头不支持进度条或时间跳转')
        assert self._cap is not None
        index = max(0, int(round(time_s * self._fps)))
        if self._frame_count:
            index = min(index, self._frame_count - 1)
        if not self._cap.set(cv2.CAP_PROP_POS_FRAMES, index) and index != 0:
            raise InvalidFrame('Video decoder does not support seeking')
        self._next_index = index
        # User-requested seek is a new inspection segment; restart exactly
        # as when main1_chn.py constructs a fresh WaterDetector.
        self._candidate_stage = None
        self._candidate_count = 0
        self._active_stage = None
        if self._mode == 'auto':
            self._detector = None
        else:
            assert self._detector is not None
            old = self._detector
            self._detector = RoiWaterDetector((self._height, self._width), self._fps,
                                           old.calib, self._config)
        self._history.clear()

    def seek(self, req: VideoSeekInput) -> dict:
        with self._lock:
            self._verify(req.session_id)
            self._seek_capture(req.time_s)
            return self._next_locked()

    def next(self, req: VideoNextInput) -> dict:
        with self._live_cv:
            self._verify(req.session_id)
            if self._source_kind != 'file':
                deadline = time.monotonic() + 5.0
                while (self._live_serial <= self._live_served and not self._live_error
                       and time.monotonic() < deadline):
                    self._live_cv.wait(timeout=max(0.0, deadline - time.monotonic()))
                    self._verify(req.session_id)
                if self._live_error:
                    raise InvalidFrame(self._live_error)
                if self._live_packet is None or self._live_serial <= self._live_served:
                    raise InvalidFrame('等待实时画面超时，请检查摄像头连接')
                self._live_served = self._live_serial
                # Snapshot a consistent analyzed image/ROI under the lock,
                # but JPEG encoding happens outside it. Otherwise the camera
                # cannot process the next source frame while the UI is served.
                packet = dict(self._live_packet)
                frame = self._last_raw_frame
                detector = self._detector
                overlay = self._live_overlay_result
            else:
                return self._next_file_locked(req)

        started = time.perf_counter()
        packet['jpeg_base64'] = self._encode_preview(frame, detector, overlay)
        packet['performance'] = {
            **packet['performance'],
            'preview_ms': round((time.perf_counter() - started) * 1000, 2),
        }
        return packet

    def _next_file_locked(self, req: VideoNextInput) -> dict:
        if req.batch_frames == 1:
            return self._next_locked()
        # On HD files, sending one JSON+JPEG per decoded frame is often
        # slower than inference itself. Preserve all temporal samples but
        # only annotate and encode the last frame in this batch.
        packet = None
        intermediate = []
        total_decode_ms = 0.0
        total_analysis_ms = 0.0
        count = 0
        for _ in range(req.batch_frames):
            candidate = self._next_locked(with_preview=False)
            if candidate['ended']:
                break
            if packet is not None:
                sample = dict(packet['result'])
                sample['history'] = []  # Only current frame needs chart.
                intermediate.append(sample)
            packet = candidate
            cost = candidate['performance']
            total_decode_ms += cost['decode_ms']
            total_analysis_ms += cost['analysis_ms']
            count += 1
        if packet is None:
            return {'ended': True}
        start_preview = time.perf_counter()
        packet['jpeg_base64'] = self._encode_preview(
            self._last_raw_frame, self._detector, self._live_overlay_result)
        packet['performance'] = {
            'frames': count,
            'decode_ms': round(total_decode_ms / count, 2),
            'analysis_ms': round(total_analysis_ms / count, 2),
            'preview_ms': round((time.perf_counter() - start_preview) * 1000, 2),
        }
        packet['samples'] = intermediate
        return packet

    def _live_loop(self, session_id: str | None) -> None:
        """Analyze every decoded live frame; renderer sees only the latest."""
        while True:
            started = time.monotonic()
            with self._live_cv:
                if self._live_stop or self._id != session_id:
                    return
                try:
                    packet = self._next_locked(with_preview=False)
                    if packet['ended']:
                        raise InvalidFrame('实时视频源已断开')
                except Exception:
                    self._live_error = '实时视频源读取失败，请检查连接并重新连接'
                    self._live_cv.notify_all()
                    return
                self._live_packet = packet
                self._live_serial += 1
                self._live_cv.notify_all()
            # Some virtual camera drivers return instantly and would spin.
            elapsed = time.monotonic() - started
            time.sleep(max(0.0, 1.0 / max(1.0, self._fps) - elapsed))

    def snapshot_raw(self, source: VideoSourceSettings):
        """Capture the latest camera image for calibration or reference saving."""
        if source.kind == 'file':
            raise InvalidFrame('本地视频请使用文件标注')
        with self._lock:
            if self._source_kind == source.kind and self._last_raw_frame is not None:
                return self._last_raw_frame.copy()
        cap = open_capture(source)
        try:
            ok, frame = cap.read()
            if not ok or frame is None:
                raise InvalidFrame('摄像头当前画面读取失败')
            return frame
        finally:
            cap.release()

    def _paused_result(self, stage: str, reason: str, confidence: float,
                       scores: dict[str, float], time_s: float, index: int) -> dict:
        """Unknown/unstable positions MUST NOT count as OK or NG."""
        return {
            'session_id': self._id, 'frame_index': index,
            'status': 'PAUSED', 'reason': reason,
            'stage': stage, 'position_confidence': confidence,
            'position_scores': scores, 's_water': 0.0,
            'history_ready': False,
            's_water_threshold': self._config.s_water_threshold,
            'sector_threshold': self._config.sector_threshold,
            'sector_count': self._config.sector_count,
            'inner_radius_ratio': self._config.inner_radius_ratio,
            'outer_radius_ratio': self._config.outer_radius_ratio,
            'max_sector_idx': -1, 'max_sector_score': 0.0,
            'sector_scores': [0.0] * self._config.sector_count,
            'abnormal_run_s': 0.0, 'time_s': time_s, 'history': [],
        }

    def _auto_select(self, frame: object) -> tuple[str, float, dict[str, float], str]:
        assert self._recognizer is not None
        candidate, confidence, scores = self._recognizer.classify(frame)
        if candidate == 'UNKNOWN':
            self._candidate_stage = None
            self._candidate_count = 0
            self._active_stage = None
            self._detector = None
            self._history.clear()
            return candidate, confidence, scores, 'POSITION_UNKNOWN'
        if candidate == self._active_stage and self._detector is not None:
            return candidate, confidence, scores, ''
        if candidate != self._candidate_stage:
            self._candidate_stage = candidate
            self._candidate_count = 1
        else:
            self._candidate_count += 1
        # Reset immediately when leaving the last confirmed position.
        self._active_stage = None
        self._detector = None
        self._history.clear()
        if self._candidate_count < 3:
            return candidate, confidence, scores, 'POSITION_UNSTABLE'
        cal = self._stage_calibrations[candidate]['calibration']
        self._detector = RoiWaterDetector((self._height, self._width), self._fps,
                                       Calibration(cal['cx'], cal['cy'], cal['radius']),
                                       self._config)
        self._active_stage = candidate
        return candidate, confidence, scores, ''

    @staticmethod
    def _encode_preview(frame, detector, data: dict | None) -> str:
        preview = (resize_display_frame(frame) if data is None
                   else render_detection_frame(frame, detector, data))
        ok_jpeg, encoded = cv2.imencode('.jpg', preview,
                                        [cv2.IMWRITE_JPEG_QUALITY, 76])
        if not ok_jpeg:
            raise InvalidFrame('Cannot encode annotated preview')
        return base64.b64encode(encoded).decode('ascii')

    def _next_locked(self, with_preview: bool = True) -> dict:
        assert self._cap is not None
        started = time.perf_counter()
        if self._probe_frame is not None:
            frame = self._probe_frame
            self._probe_frame = None
            ok = True
        else:
            ok, frame = self._cap.read()
        if not ok or frame is None:
            return {'ended': True}
        self._last_raw_frame = frame
        decoded_at = time.perf_counter()
        index = self._next_index
        self._next_index += 1
        t = index / self._fps
        # The recognizer never edits the frame. The canonical WaterDetector
        # still processes the original full-FPS decoded BGR image.
        stage, confidence, scores, reason = ('P1', 1.0, {}, '')
        if not self._detecting:
            reason = 'DETECTION_STOPPED'
        elif self._mode == 'auto':
            stage, confidence, scores, reason = self._auto_select(frame)
        if reason:
            data = None
        else:
            assert self._detector is not None
            data = self._detector.process(frame)
        if not with_preview:
            # Keep the last inference mask until /next requests this frame.
            self._live_overlay_result = data
        if data is not None:
            self._history.append({'time_s': t, 's_water': float(data['s_water'])})
            while self._history and self._history[0]['time_s'] < t - 5.0:
                self._history.popleft()
        result = self._paused_result(stage, reason, confidence, scores, t, index) if reason else {
                'session_id': self._id,
                'frame_index': index,
                'status': data['status'], 'reason': '',
                'stage': stage, 'position_confidence': confidence,
                'position_scores': scores,
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
            }
        analyzed_at = time.perf_counter()
        packet = {'ended': False, 'frame_index': index, 'time_s': t,
                  'result': result, 'detecting': self._detecting,
                  'performance': {
                      'frames': 1,
                      'decode_ms': round((decoded_at - started) * 1000, 2),
                      'analysis_ms': round((analyzed_at - decoded_at) * 1000, 2),
                      'preview_ms': 0.0,
                  }}
        if with_preview:
            packet['jpeg_base64'] = self._encode_preview(frame, self._detector, data)
            packet['performance']['preview_ms'] = round(
                (time.perf_counter() - analyzed_at) * 1000, 2)
        return packet
