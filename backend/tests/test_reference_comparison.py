"""Unit tests for deterministic 8 FPS same-frame reference comparisons."""
from dataclasses import replace

import numpy as np

from sample_backend.services.reference_comparison import (
    collect_reference, run_candidate, sample_frames, score_comparison,
    tune_candidates, SAMPLE_FPS,
)
from sample_backend.services.water_detection import Calibration, DemoConfig


def small_frames(count=60):
    for i in range(count):
        frame = np.full((64, 64, 3), 85, dtype=np.uint8)
        frame[12:50, 12:50] = (35 + (i * 13) % 150)
        yield frame


def test_original_video_time_bucket_matches_renderer_sampler():
    samples = list(sample_frames(small_frames(30), 30))
    assert [i for i, _, _ in samples] == [0, 4, 8, 12, 15, 19, 23, 27]
    assert len(list(sample_frames(small_frames(25), 25))) == 8


def test_same_decoded_frames_fed_to_both_original_and_eight_fps_detectors():
    calib = Calibration(32, 32, 24)
    cfg = DemoConfig()
    packets = collect_reference(small_frames(), 30, calib, cfg)
    assert len(packets) == 16
    assert packets[0]['frame_id'] == 0
    assert packets[1]['frame_id'] == 4
    result = run_candidate(packets, calib, cfg)
    assert len(result) == len(packets)
    assert result[0]['original_status'] == 'WARMUP'
    assert result[0]['sampled_status'] == 'WARMUP'
    assert result[-1]['original_ready'] and result[-1]['sampled_ready']
    metrics = score_comparison(result)
    assert metrics['compared_frames'] > 0


def test_grid_search_only_adjusts_frame_activity_and_persistence_not_ng_threshold():
    calib = Calibration(32, 32, 24)
    cfg = DemoConfig()
    packets = collect_reference(small_frames(80), 30, calib, cfg)
    best = tune_candidates(packets, calib, cfg)
    assert best
    assert best[0]['score'] <= best[-1]['score']
    for item in best:
        assert 0 <= item['status_agreement'] <= 1
        assert 's_water_threshold' not in item
