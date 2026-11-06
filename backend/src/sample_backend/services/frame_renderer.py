"""Display-only ring renderer matching main1_chn.py draw_ring_and_sectors.

This function runs AFTER WaterDetector.process(). JPEG compression is applied
only to the annotated preview, never to the frames passed to the detector.
"""
from __future__ import annotations

import math
from typing import Sequence

import cv2
import numpy as np

from .water_detection import WaterDetector


def render_detection_frame(frame: np.ndarray, detector: WaterDetector, result: dict) -> np.ndarray:
    out = frame.copy()
    cfg = detector.cfg
    c = (int(round(detector.calib.cx)), int(round(detector.calib.cy)))
    r_in = int(round(cfg.inner_radius_ratio * detector.calib.radius))
    r_out = int(round(cfg.outer_radius_ratio * detector.calib.radius))

    # Original main1_chn.py display overlay, not part of detection computation.
    persistent = result.get("persistent")
    if persistent is not None:
        red = np.zeros_like(out)
        red[..., 2] = 255
        mask_u8 = persistent.astype(np.uint8) * 255
        blend = cv2.addWeighted(out, 0.55, red, 0.45, 0)
        out[mask_u8 > 0] = blend[mask_u8 > 0]

    cv2.circle(out, c, r_in, (255, 180, 0), 2)
    cv2.circle(out, c, r_out, (0, 255, 0), 2)
    n = cfg.sector_count
    sector_scores: Sequence[float] = result.get("sector_scores", [])
    for k in range(n):
        a = 2.0 * math.pi * k / n
        p1 = (int(round(c[0] + r_in * math.cos(a))),
              int(round(c[1] + r_in * math.sin(a))))
        p2 = (int(round(c[0] + r_out * math.cos(a))),
              int(round(c[1] + r_out * math.sin(a))))
        cv2.line(out, p1, p2, (100, 100, 100), 1, cv2.LINE_AA)
    for k, score in enumerate(sector_scores):
        if score >= cfg.sector_threshold:
            start_deg = 360.0 * k / n
            end_deg = 360.0 * (k + 1) / n
            cv2.ellipse(out, c, (r_out, r_out), 0, start_deg, end_deg,
                        (0, 0, 255), 5, cv2.LINE_AA)
    return out
