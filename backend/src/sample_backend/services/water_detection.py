"""Original main1_chn.py water-flow detector, without the OpenCV GUI.

Calculation order, thresholds, warmup and NG/OK hysteresis are preserved.
The desktop app provides decoded frames from the visible video element.
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from typing import Deque, List, Optional, Tuple
import cv2
import numpy as np

@dataclass
class DemoConfig:
    # 环形 ROI：只看晶圆外缘
    inner_radius_ratio: float = 0.65
    outer_radius_ratio: float = 0.95

    # 相邻帧差阈值（8-bit 灰度）
    diff_threshold: float = 8.0

    # 时序驻留参数
    history_seconds: float = 0.50
    persistence_threshold: float = 0.50

    # 整体异常阈值：persistent water area / ring ROI area
    s_water_threshold: float = 0.025

    # 连续异常多久才进入 NG
    ng_hold_seconds: float = 0.50

    # 连续恢复多久才从 NG 回到 OK
    recover_hold_seconds: float = 0.60

    # 扇区
    sector_count: int = 24
    sector_threshold: float = 0.05

    # 预处理
    blur_ksize: int = 3

    # 可视化
    panel_width: int = 330
    graph_seconds: float = 5.0


@dataclass
class Calibration:
    cx: float
    cy: float
    radius: float


class WaterDetector:
    def __init__(self, shape_hw: Tuple[int, int], fps: float, calib: Calibration, cfg: DemoConfig):
        self.h, self.w = shape_hw
        self.fps = fps if fps > 1e-6 else 30.0
        self.calib = calib
        self.cfg = cfg

        self.history_frames = max(2, int(round(cfg.history_seconds * self.fps)))
        self.activity_history: Deque[np.ndarray] = deque(maxlen=self.history_frames)
        self.score_history: Deque[float] = deque(maxlen=max(10, int(round(cfg.graph_seconds * self.fps))))

        self.prev_gray: Optional[np.ndarray] = None
        self.abnormal_run_s = 0.0
        self.recover_run_s = 0.0
        self.status = "WARMUP"

        self._build_geometry()

    def _build_geometry(self) -> None:
        yy, xx = np.mgrid[0:self.h, 0:self.w]
        dx = xx.astype(np.float32) - float(self.calib.cx)
        dy = yy.astype(np.float32) - float(self.calib.cy)

        r = np.sqrt(dx * dx + dy * dy)
        self.phi = (np.arctan2(dy, dx) + 2.0 * np.pi) % (2.0 * np.pi)

        inner = self.cfg.inner_radius_ratio * self.calib.radius
        outer = self.cfg.outer_radius_ratio * self.calib.radius
        self.roi = (r >= inner) & (r <= outer)
        self.roi_count = int(np.count_nonzero(self.roi))
        if self.roi_count < 100:
            raise ValueError("ROI 太小，请检查晶圆中心/半径标定。")

        self.sector_masks: List[np.ndarray] = []
        self.sector_counts: List[int] = []
        n = self.cfg.sector_count
        for k in range(n):
            a0 = 2.0 * np.pi * k / n
            a1 = 2.0 * np.pi * (k + 1) / n
            m = self.roi & (self.phi >= a0) & (self.phi < a1)
            self.sector_masks.append(m)
            self.sector_counts.append(max(1, int(np.count_nonzero(m))))

    def _prep_gray(self, frame: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        k = int(self.cfg.blur_ksize)
        if k >= 3:
            if k % 2 == 0:
                k += 1
            gray = cv2.GaussianBlur(gray, (k, k), 0)
        return gray

    def process(self, frame: np.ndarray) -> dict:
        gray = self._prep_gray(frame)
        dt = 1.0 / self.fps

        # 第一帧：没有帧差
        if self.prev_gray is None:
            self.prev_gray = gray
            self.score_history.append(0.0)
            return self._empty_result()

        cur = gray.astype(np.float32)
        pre = self.prev_gray.astype(np.float32)
        signed_diff = cur - pre

        # 去掉 ROI 内整体亮度的同步漂移，降低自动曝光/环境亮度小变化的影响
        global_change = float(np.median(signed_diff[self.roi]))
        diff = np.abs(signed_diff - global_change)

        active = (diff > self.cfg.diff_threshold) & self.roi
        self.activity_history.append(active)
        self.prev_gray = gray

        # history 未填满时先 warmup，避免刚开始就误判
        if len(self.activity_history) < self.history_frames:
            self.score_history.append(0.0)
            return self._empty_result(active=active, diff=diff)

        # [T,H,W] -> [H,W]，表示最近 history 中每个像素有多少比例的时间在变化
        stack = np.stack(self.activity_history, axis=0)
        persistence = stack.mean(axis=0)
        persistent = (persistence >= self.cfg.persistence_threshold) & self.roi

        s_water = float(np.count_nonzero(persistent) / self.roi_count)

        sector_scores: List[float] = []
        for m, cnt in zip(self.sector_masks, self.sector_counts):
            score = float(np.count_nonzero(persistent & m) / cnt)
            sector_scores.append(score)

        max_sector_idx = int(np.argmax(sector_scores)) if sector_scores else -1
        max_sector_score = sector_scores[max_sector_idx] if max_sector_idx >= 0 else 0.0

        instant_abnormal = s_water >= self.cfg.s_water_threshold

        # 状态机：进入 NG 与恢复使用不同的持续时间，减少抖动
        if instant_abnormal:
            self.abnormal_run_s += dt
            self.recover_run_s = 0.0
        else:
            self.recover_run_s += dt
            if self.status != "NG":
                self.abnormal_run_s = 0.0

        if self.status in ("WARMUP", "OK"):
            if self.abnormal_run_s >= self.cfg.ng_hold_seconds:
                self.status = "NG"
            else:
                self.status = "OK"
        elif self.status == "NG":
            if instant_abnormal:
                self.recover_run_s = 0.0
            elif self.recover_run_s >= self.cfg.recover_hold_seconds:
                self.status = "OK"
                self.abnormal_run_s = 0.0
                self.recover_run_s = 0.0

        self.score_history.append(s_water)

        return {
            "status": self.status,
            "s_water": s_water,
            "active": active,
            "persistent": persistent,
            "persistence": persistence,
            "diff": diff,
            "global_change": global_change,
            "sector_scores": sector_scores,
            "max_sector_idx": max_sector_idx,
            "max_sector_score": max_sector_score,
            "abnormal_run_s": self.abnormal_run_s,
            "history_ready": True,
        }

    def _empty_result(self, active: Optional[np.ndarray] = None, diff: Optional[np.ndarray] = None) -> dict:
        if self.status == "WARMUP" and len(self.activity_history) >= self.history_frames:
            self.status = "OK"
        return {
            "status": "WARMUP" if len(self.activity_history) < self.history_frames else self.status,
            "s_water": 0.0,
            "active": active,
            "persistent": None,
            "persistence": None,
            "diff": diff,
            "global_change": 0.0,
            "sector_scores": [0.0] * self.cfg.sector_count,
            "max_sector_idx": -1,
            "max_sector_score": 0.0,
            "abnormal_run_s": self.abnormal_run_s,
            "history_ready": False,
        }
