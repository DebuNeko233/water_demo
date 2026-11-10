"""Exact frame-by-frame regression against the unchanged full-frame detector."""
import base64

import cv2
import numpy as np
import pytest

from sample_backend.services.water_detection import Calibration, DemoConfig, WaterDetector
from sample_backend.services.roi_detector import RoiWaterDetector
from sample_backend.services.frame_renderer import render_detection_frame, DISPLAY_MAX_EDGE


def frames(height, width, count=18):
    yy, xx = np.indices((height, width))
    for n in range(count):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[..., 0] = ((xx // 9 + 5 * n) % 210 + 15).astype(np.uint8)
        frame[..., 1] = ((yy // 7 + 3 * n) % 180 + 25).astype(np.uint8)
        frame[..., 2] = ((xx // 11 + yy // 13 + 7 * n) % 200 + 20).astype(np.uint8)
        yield frame


@pytest.mark.parametrize('cx,cy,radius', [
    (310.5, 170.25, 71.5),
    (36.4, 39.75, 118.3),  # Circular ROI clipped by top and left edges
])
@pytest.mark.parametrize('blur', [0, 3, 5])
def test_rolling_roi_detector_matches_full_frame_detector_every_frame(cx, cy, radius, blur):
    shape = (360, 640)
    cfg = DemoConfig(blur_ksize=blur, history_seconds=0.35,
                     persistence_threshold=0.40, sector_count=24,
                     ng_hold_seconds=0.25, recover_hold_seconds=0.33)
    cal = Calibration(cx, cy, radius)
    original = WaterDetector(shape, 12, cal, cfg)
    optimized = RoiWaterDetector(shape, 12, cal, cfg)
    x0, y0, x1, y1 = optimized.bounds
    assert x1 - x0 < shape[1] or y1 - y0 < shape[0]

    for number, frame in enumerate(frames(*shape)):
        truth = original.process(frame)
        result = optimized.process(frame)
        for key in ('status', 'history_ready', 's_water', 'max_sector_idx',
                    'max_sector_score', 'sector_scores', 'abnormal_run_s',
                    'global_change'):
            assert result[key] == truth[key], (number, blur, key, truth[key], result[key])
        for key in ('active', 'persistent'):
            baseline = truth[key]
            actual = result[key]
            if baseline is None:
                assert actual is None
            else:
                np.testing.assert_array_equal(actual, baseline[y0:y1, x0:x1])
        assert len(optimized._inner.activity_history) <= optimized._inner.history_frames


def test_1080p_preview_is_smaller_without_scaling_detection_geometry():
    height, width = 1080, 1920
    frame = np.full((height, width, 3), 90, np.uint8)
    original_copy = frame.copy()
    detector = RoiWaterDetector((height, width), 30,
                                Calibration(900, 530, 145), DemoConfig())
    result = detector.process(frame)
    preview = render_detection_frame(frame, detector, result)
    assert preview.shape == (540, DISPLAY_MAX_EDGE, 3)
    assert detector.bounds[2] - detector.bounds[0] < 350
    np.testing.assert_array_equal(frame, original_copy)


def test_scaled_persistent_overlay_does_not_modify_detection_masks():
    height, width = 1080, 1920
    frame = np.full((height, width, 3), 140, np.uint8)
    detector = RoiWaterDetector((height, width), 30,
                                Calibration(900, 530, 145), DemoConfig())
    detector.process(frame)
    x0, y0, x1, y1 = detector.bounds
    marker = np.zeros((y1 - y0, x1 - x0), dtype=bool)
    marker[30:50, 30:50] = True
    original = marker.copy()
    result = {'persistent': marker, 'sector_scores': [0.0] * 24}
    preview = render_detection_frame(frame, detector, result)
    assert preview.shape == (540, 960, 3)
    assert np.any(preview[..., 2] > 150)
    np.testing.assert_array_equal(marker, original)
