"""Optimized implementation of the original WaterDetector for high-resolution sources.

Detection stays in original source pixels and sees EVERY decoded frame.
Only the bounding rectangle containing the existing annular ROI is calculated.
An incremental integer count replaces np.stack(...).mean() for each frame.
The original WaterDetector is retained as an independent reference baseline.
"""
from __future__ import annotations

import math
from collections import deque

import numpy as np

from .water_detection import Calibration, DemoConfig, WaterDetector


class _RollingWaterDetector(WaterDetector):
    """Mathematically equivalent per-pixel history without repeated 3-D stacks."""

    def __init__(self, shape_hw: tuple[int, int], fps: float, calib: Calibration,
                 cfg: DemoConfig, origin_x: int, origin_y: int):
        self._origin_x = origin_x
        self._origin_y = origin_y
        self._source_calib = calib
        crop_cal = Calibration(calib.cx - origin_x, calib.cy - origin_y, calib.radius)
        super().__init__(shape_hw, fps, crop_cal, cfg)
        self._rolling_count = np.zeros((self.h, self.w), dtype=np.uint16)

    def _build_geometry(self) -> None:
        # Use the SAME source-pixel coordinates and float32 operations as the
        # original full-frame implementation to preserve sector boundaries.
        yy, xx = np.mgrid[
            self._origin_y:self._origin_y + self.h,
            self._origin_x:self._origin_x + self.w,
        ]
        dx = xx.astype(np.float32) - float(self._source_calib.cx)
        dy = yy.astype(np.float32) - float(self._source_calib.cy)
        radius = np.sqrt(dx * dx + dy * dy)
        self.phi = (np.arctan2(dy, dx) + 2.0 * np.pi) % (2.0 * np.pi)

        inner = self.cfg.inner_radius_ratio * self._source_calib.radius
        outer = self.cfg.outer_radius_ratio * self._source_calib.radius
        self.roi = (radius >= inner) & (radius <= outer)
        self.roi_count = int(np.count_nonzero(self.roi))
        if self.roi_count < 100:
            raise ValueError('ROI 太小，请检查晶圆中心/半径标定。')

        self.sector_masks = []
        self.sector_counts = []
        n = self.cfg.sector_count
        for k in range(n):
            a0 = 2.0 * np.pi * k / n
            a1 = 2.0 * np.pi * (k + 1) / n
            mask = self.roi & (self.phi >= a0) & (self.phi < a1)
            self.sector_masks.append(mask)
            self.sector_counts.append(max(1, int(np.count_nonzero(mask))))
        # Sector membership is immutable for this calibration; a single
        # bincount over persistent pixels replaces 24 full-mask scans/frame.
        self._sector_ids = np.full((self.h, self.w), -1, dtype=np.int16)
        for k, mask in enumerate(self.sector_masks):
            self._sector_ids[mask] = k

    def process(self, frame: np.ndarray) -> dict:
        gray = self._prep_gray(frame)
        dt = 1.0 / self.fps

        if self.prev_gray is None:
            self.prev_gray = gray
            self.score_history.append(0.0)
            return self._empty_result()

        cur = gray.astype(np.float32)
        pre = self.prev_gray.astype(np.float32)
        signed_diff = cur - pre
        global_change = float(np.median(signed_diff[self.roi]))
        diff = np.abs(signed_diff - global_change)
        active = (diff > self.cfg.diff_threshold) & self.roi

        # Evict before append, since deque(maxlen=...) otherwise evicts
        # implicitly and we would lose track of the outgoing contribution.
        if len(self.activity_history) == self.history_frames:
            oldest = self.activity_history.popleft()
            self._rolling_count -= oldest
        self.activity_history.append(active)
        self._rolling_count += active
        self.prev_gray = gray

        if len(self.activity_history) < self.history_frames:
            self.score_history.append(0.0)
            return self._empty_result(active=active, diff=diff)

        # An integer count over N frames equals stack.mean(axis=0) over the
        # same boolean history; no 3-D allocation is required per new frame.
        persistence = self._rolling_count.astype(np.float64) / self.history_frames
        persistent = (persistence >= self.cfg.persistence_threshold) & self.roi
        s_water = float(np.count_nonzero(persistent) / self.roi_count)

        persistent_sectors = self._sector_ids[persistent]
        sector_hits = np.bincount(persistent_sectors[persistent_sectors >= 0],
                                  minlength=self.cfg.sector_count)
        sector_scores = [
            float(hit / count)
            for hit, count in zip(sector_hits, self.sector_counts)
        ]
        max_sector_idx = int(np.argmax(sector_scores)) if sector_scores else -1
        max_sector_score = sector_scores[max_sector_idx] if max_sector_idx >= 0 else 0.0

        instant_abnormal = s_water >= self.cfg.s_water_threshold
        if instant_abnormal:
            self.abnormal_run_s += dt
            self.recover_run_s = 0.0
        else:
            self.recover_run_s += dt
            if self.status != 'NG':
                self.abnormal_run_s = 0.0

        if self.status in ('WARMUP', 'OK'):
            if self.abnormal_run_s >= self.cfg.ng_hold_seconds:
                self.status = 'NG'
            else:
                self.status = 'OK'
        elif self.status == 'NG':
            if instant_abnormal:
                self.recover_run_s = 0.0
            elif self.recover_run_s >= self.cfg.recover_hold_seconds:
                self.status = 'OK'
                self.abnormal_run_s = 0.0
                self.recover_run_s = 0.0

        self.score_history.append(s_water)
        return {
            'status': self.status,
            's_water': s_water,
            'active': active,
            'persistent': persistent,
            'persistence': persistence,
            'diff': diff,
            'global_change': global_change,
            'sector_scores': sector_scores,
            'max_sector_idx': max_sector_idx,
            'max_sector_score': max_sector_score,
            'abnormal_run_s': self.abnormal_run_s,
            'history_ready': True,
        }


class RoiWaterDetector:
    """Source-sized pixel coordinates, bounded math and original calibration."""

    def __init__(self, shape_hw: tuple[int, int], fps: float,
                 calib: Calibration, cfg: DemoConfig):
        height, width = shape_hw
        outer = cfg.outer_radius_ratio * calib.radius
        blur_margin = max(0, int(cfg.blur_ksize) // 2) + 2
        x0 = max(0, int(math.floor(calib.cx - outer)) - blur_margin)
        x1 = min(width, int(math.ceil(calib.cx + outer)) + blur_margin + 1)
        y0 = max(0, int(math.floor(calib.cy - outer)) - blur_margin)
        y1 = min(height, int(math.ceil(calib.cy + outer)) + blur_margin + 1)
        if x0 >= x1 or y0 >= y1:
            raise ValueError('ROI 不在视频画面内')
        self.bounds = (x0, y0, x1, y1)
        self.calib = calib  # Original full-source pixel geometry for overlays.
        self.cfg = cfg
        self._inner = _RollingWaterDetector(
            (y1 - y0, x1 - x0), fps, calib, cfg, x0, y0)

    def process(self, frame: np.ndarray) -> dict:
        x0, y0, x1, y1 = self.bounds
        return self._inner.process(frame[y0:y1, x0:x1])
