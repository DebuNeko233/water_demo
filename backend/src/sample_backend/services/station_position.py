"""Device-local three-station ROI calibration and reference screenshots.

The reference images are decoded directly by OpenCV from the source video,
not round-tripped through a browser JPEG. This component is independent of the
canonical main1_chn.py WaterDetector; it selects which calibration to use.
"""
from __future__ import annotations

import json
import math
import os
import threading
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
from pydantic import BaseModel, Field, model_validator

from .water_session import CalibrationInput, InvalidFrame
from sample_backend.core.config import data_directory

STAGES = ("P1", "P2", "P3")
MIN_REFS = 5
MAX_REFS = 12


class StageCalibrationInput(BaseModel):
    stage: str
    calibration: CalibrationInput


class StageReferenceInput(BaseModel):
    stage: str
    file_path: str = Field(min_length=1, max_length=4096)
    time_s: float = Field(ge=0, le=86400, allow_inf_nan=False)


class StageRemoveReferenceInput(BaseModel):
    stage: str
    reference_id: str = Field(min_length=1, max_length=64)


class StageResetInput(BaseModel):
    stage: str


def edge_descriptor(frame: np.ndarray) -> np.ndarray:
    # Same descriptor as the reference repository, with smaller fixed input.
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, (128, 96), interpolation=cv2.INTER_AREA)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    return cv2.GaussianBlur(cv2.magnitude(gx, gy), (5, 5), 0)


class ReferencePositionRecognizer:
    """Match only stable edge features, abstain instead of guessing on ambiguity."""

    def __init__(self, samples: dict[str, list[np.ndarray]],
                 threshold: float = .78, margin: float = .035):
        self.threshold = threshold
        self.margin = margin
        self.references: dict[str, list[np.ndarray]] = {}
        self.masks: dict[str, np.ndarray] = {}
        for stage in STAGES:
            frames = samples.get(stage, [])
            if len(frames) < MIN_REFS:
                continue
            descriptors = np.stack([edge_descriptor(f) for f in frames])
            self.references[stage] = [x for x in descriptors]
            # Moving nozzle/water creates edges that vary from reference to
            # reference; downweight them. Preserve bright wafer-rim features.
            median = np.median(descriptors, axis=0)
            spread = np.median(np.abs(descriptors - median), axis=0)
            stable = np.clip(1.0 - spread / (median + 10.0), 0.15, 1.0)
            self.masks[stage] = stable.astype(np.float32)

    @property
    def ready(self) -> bool:
        return all(len(self.references.get(s, [])) >= MIN_REFS for s in STAGES)

    @staticmethod
    def _corr(current: np.ndarray, ref: np.ndarray, weights: np.ndarray) -> float:
        # Weighted cosine-like correlation with mean subtraction.
        total = float(np.sum(weights))
        if total <= 0:
            return -1.0
        a = current - np.sum(current * weights) / total
        b = ref - np.sum(ref * weights) / total
        numerator = float(np.sum(weights * a * b))
        denom = math.sqrt(float(np.sum(weights * a * a)) *
                          float(np.sum(weights * b * b)))
        return numerator / denom if denom > 1e-8 else -1.0

    def classify(self, frame: np.ndarray) -> tuple[str, float, dict[str, float]]:
        if not self.ready:
            return "UNKNOWN", 0.0, {}
        descriptor = edge_descriptor(frame)
        scores = {}
        for stage in STAGES:
            # Robust against an atypical nozzle position in one reference.
            values = [self._corr(descriptor, ref, self.masks[stage])
                      for ref in self.references[stage]]
            scores[stage] = float(np.median(values))
        ordered = sorted(scores.items(), key=lambda p: p[1], reverse=True)
        best, second = ordered[:2]
        if best[1] < self.threshold or best[1] - second[1] < self.margin:
            return "UNKNOWN", best[1], scores
        return best[0], best[1], scores


class StageProfileStore:
    """One local equipment profile, explicitly saved by calibration UI."""
    def __init__(self, root: Path | None = None):
        self.root = root if root is not None else data_directory() / 'stations'
        self._lock = threading.RLock()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'profile.json'
        self._profile = self._read()

    def _read(self) -> dict:
        if not self.path.exists():
            return {'version': 1, 'stages': {
                s: {'calibration': None, 'references': []} for s in STAGES}}
        obj = json.loads(self.path.read_text(encoding='utf-8'))
        for s in STAGES:
            obj['stages'][s]['calibration'] = (
                CalibrationInput.model_validate(obj['stages'][s]['calibration']).model_dump()
                if obj['stages'][s]['calibration'] else None)
            for ref in obj['stages'][s]['references']:
                if not ref['id'].isalnum():
                    raise ValueError('Invalid stage reference ID')
        return obj

    def _save(self) -> None:
        tmp = self.path.with_name(uuid4().hex + '.tmp')
        try:
            tmp.write_text(json.dumps(self._profile, indent=2), encoding='utf-8')
            os.replace(tmp, self.path)
        finally:
            tmp.unlink(missing_ok=True)

    def snapshot(self) -> dict:
        with self._lock:
            snapshot = json.loads(json.dumps(self._profile))
            snapshot['ready'] = all(
                snapshot['stages'][s]['calibration'] is not None and
                len(snapshot['stages'][s]['references']) >= MIN_REFS
                for s in STAGES)
            snapshot['minimum_references'] = MIN_REFS
            return snapshot

    @staticmethod
    def _stage(stage: str) -> str:
        if stage not in STAGES:
            raise InvalidFrame('工位只能是 P1/P2/P3')
        return stage

    def calibrate(self, req: StageCalibrationInput) -> dict:
        stage = self._stage(req.stage)
        with self._lock:
            old = self._profile['stages'][stage]
            calibration = req.calibration.model_dump()
            # Invalidate reference images when a calibration changes size;
            # keeping old references would silently compare different devices.
            clear = old['calibration'] is not None and (
                old['calibration']['width'], old['calibration']['height']) != (
                calibration['width'], calibration['height'])
            new = {'calibration': calibration,
                   'references': [] if clear else list(old['references'])}
            self._profile['stages'][stage] = new
            try:
                self._save()
            except Exception:
                self._profile['stages'][stage] = old
                raise
            if clear:
                for ref in old['references']:
                    (self.root / (ref['id'] + '.png')).unlink(missing_ok=True)
            return self.snapshot()

    def capture(self, req: StageReferenceInput) -> dict:
        stage = self._stage(req.stage)
        with self._lock:
            entry = self._profile['stages'][stage]
            if entry['calibration'] is None:
                raise InvalidFrame('请先标注该工位晶圆 ROI')
            if len(entry['references']) >= MAX_REFS:
                raise InvalidFrame('每个工位最多 12 张参考图')
            path = Path(req.file_path)
            if path.suffix.lower() not in {'.mp4', '.mov', '.mkv', '.avi', '.m4v', '.webm'} or not path.is_file():
                raise InvalidFrame('视频文件不存在或格式不支持')
            cap = cv2.VideoCapture(str(path))
            if not cap.isOpened():
                raise InvalidFrame('无法解码参考视频')
            try:
                fps = float(cap.get(cv2.CAP_PROP_FPS))
                if not math.isfinite(fps) or fps < 1:
                    raise InvalidFrame('视频帧率无效')
                index = max(0, int(round(req.time_s * fps)))
                cap.set(cv2.CAP_PROP_POS_FRAMES, index)
                ok, frame = cap.read()
                if not ok:
                    raise InvalidFrame('参考帧不可读取')
                h, w = frame.shape[:2]
                cal = entry['calibration']
                if (w, h) != (cal['width'], cal['height']):
                    raise InvalidFrame('参考帧分辨率与标定不一致')
                if any(abs(ref['time_s'] - req.time_s) < 0.12 and
                       ref['source'] == path.name for ref in entry['references']):
                    raise InvalidFrame('参考帧与已有截图太接近，请选择不同画面')
                # Persist real lossless source frame for subsequent sessions.
                ok, encoded = cv2.imencode('.png', frame)
                if not ok:
                    raise InvalidFrame('参考截图编码失败')
                ident = uuid4().hex
                filename = self.root / (ident + '.png')
                filename.write_bytes(encoded.tobytes())
                ref = {'id': ident, 'time_s': req.time_s, 'source': path.name}
                entry['references'].append(ref)
                try:
                    self._save()
                except Exception:
                    entry['references'].pop()
                    filename.unlink(missing_ok=True)
                    raise
                return self.snapshot()
            finally:
                cap.release()

    def remove_reference(self, req: StageRemoveReferenceInput) -> dict:
        stage = self._stage(req.stage)
        with self._lock:
            entry = self._profile['stages'][stage]
            old = list(entry['references'])
            entry['references'] = [r for r in old if r['id'] != req.reference_id]
            if len(old) == len(entry['references']):
                raise InvalidFrame('参考帧不存在')
            try:
                self._save()
            except Exception:
                entry['references'] = old
                raise
            (self.root / (req.reference_id + '.png')).unlink(missing_ok=True)
            return self.snapshot()

    def build(self, width: int, height: int) -> tuple[dict, ReferencePositionRecognizer]:
        with self._lock:
            snap = self.snapshot()
            if not snap['ready']:
                raise InvalidFrame('三个工位均须标注 ROI 且每个至少提供 5 张参考帧')
            samples: dict[str, list[np.ndarray]] = {}
            for stage in STAGES:
                cal = snap['stages'][stage]['calibration']
                if (cal['width'], cal['height']) != (width, height):
                    raise InvalidFrame('标定分辨率与当前视频不一致，请重新标定')
                samples[stage] = []
                for ref in snap['stages'][stage]['references']:
                    frame = cv2.imread(str(self.root / (ref['id'] + '.png')))
                    if frame is None or frame.shape[:2] != (height, width):
                        raise InvalidFrame('参考截图丢失或分辨率错误，请重新采集')
                    samples[stage].append(frame)
            model = ReferencePositionRecognizer(samples)
            if not model.ready:
                raise InvalidFrame('参考帧模型未就绪')
            return snap, model
