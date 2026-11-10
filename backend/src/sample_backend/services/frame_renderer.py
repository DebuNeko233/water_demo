"""Draw monitor-only overlays on a bounded preview (never on detector input).

Original coordinates and decision masks are kept at their source resolution;
the downscaled JPEG only affects what the Electron UI displays.
"""
from __future__ import annotations

import math
from typing import Sequence

import cv2
import numpy as np

from .water_detection import WaterDetector

DISPLAY_MAX_EDGE = 960


def resize_display_frame(frame: np.ndarray) -> np.ndarray:
    height, width = frame.shape[:2]
    longest = max(height, width)
    if longest <= DISPLAY_MAX_EDGE:
        return frame.copy()
    scale = DISPLAY_MAX_EDGE / longest
    size = (max(1, int(round(width * scale))),
            max(1, int(round(height * scale))))
    return cv2.resize(frame, size, interpolation=cv2.INTER_AREA)


def render_detection_frame(frame: np.ndarray, detector: WaterDetector,
                           result: dict) -> np.ndarray:
    out = resize_display_frame(frame)
    cfg = detector.cfg
    source_height, source_width = frame.shape[:2]
    out_height, out_width = out.shape[:2]
    scale_x = out_width / source_width
    scale_y = out_height / source_height
    scale = min(scale_x, scale_y)
    c = (int(round(detector.calib.cx * scale_x)),
         int(round(detector.calib.cy * scale_y)))
    r_in = int(round(cfg.inner_radius_ratio * detector.calib.radius * scale))
    r_out = int(round(cfg.outer_radius_ratio * detector.calib.radius * scale))

    persistent = result.get('persistent')
    if persistent is not None:
        # ROI detector returns only the relevant cropped mask. Painting the
        # original 1080p red overlay would waste multiple full-size buffers.
        bounds = getattr(detector, 'bounds', (0, 0, source_width, source_height))
        x0, y0, x1, y1 = bounds
        left = max(0, min(out_width, int(round(x0 * scale_x))))
        right = max(left, min(out_width, int(round(x1 * scale_x))))
        top = max(0, min(out_height, int(round(y0 * scale_y))))
        bottom = max(top, min(out_height, int(round(y1 * scale_y))))
        region = out[top:bottom, left:right]
        if region.size:
            if persistent.shape[:2] != region.shape[:2]:
                mask = cv2.resize(persistent.astype(np.uint8),
                                  (region.shape[1], region.shape[0]),
                                  interpolation=cv2.INTER_NEAREST)
            else:
                mask = persistent
            red = np.zeros_like(region)
            red[..., 2] = 255
            blend = cv2.addWeighted(region, 0.55, red, 0.45, 0)
            region[mask > 0] = blend[mask > 0]

    cv2.circle(out, c, r_in, (255, 180, 0), max(1, int(round(2 * scale))))
    cv2.circle(out, c, r_out, (0, 255, 0), max(1, int(round(2 * scale))))
    n = cfg.sector_count
    sector_scores: Sequence[float] = result.get('sector_scores', [])
    for k in range(n):
        angle = 2.0 * math.pi * k / n
        p1 = (int(round(c[0] + r_in * math.cos(angle))),
              int(round(c[1] + r_in * math.sin(angle))))
        p2 = (int(round(c[0] + r_out * math.cos(angle))),
              int(round(c[1] + r_out * math.sin(angle))))
        cv2.line(out, p1, p2, (100, 100, 100), 1, cv2.LINE_AA)
    for k, score in enumerate(sector_scores):
        if score >= cfg.sector_threshold:
            start_deg = 360.0 * k / n
            end_deg = 360.0 * (k + 1) / n
            cv2.ellipse(out, c, (r_out, r_out), 0, start_deg, end_deg,
                        (0, 0, 255), max(1, int(round(5 * scale))),
                        cv2.LINE_AA)
    return out
