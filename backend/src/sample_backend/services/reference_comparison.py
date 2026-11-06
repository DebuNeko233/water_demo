"""Reproducible 30 FPS vs 8 FPS comparison on exactly the same decoded frames.

The original WaterDetector processes every source frame. The same decoded
frames are selected on a fixed 8 Hz video-time lattice for a second detector.
No JPEG encode/decode is used, and all unchanged parameters are inherited
from the original main1_chn.py DemoConfig.

A best-fit result for one video is a CANDIDATE, not a production threshold:
validation against independent known-good and known-NG videos is required.
"""
from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, replace
from pathlib import Path
from typing import Iterable, Iterator

import cv2
import numpy as np

from .water_detection import Calibration, DemoConfig, WaterDetector

SAMPLE_FPS = 8.0
TUNED_KEYS = ('diff_threshold', 'history_seconds', 'persistence_threshold')
EDITABLE_KEYS = (
    'inner_radius_ratio', 'outer_radius_ratio', 'diff_threshold',
    'history_seconds', 'persistence_threshold', 's_water_threshold',
    'ng_hold_seconds', 'recover_hold_seconds', 'sector_count',
    'sector_threshold', 'blur_ksize',
)


def sample_frames(frames: Iterable[np.ndarray], source_fps: float,
                  target_fps: float = SAMPLE_FPS) -> Iterator[tuple[int, float, np.ndarray]]:
    """Same time-bucket selection as frameSampling.mjs (video media time base 0).

    Decoding is never repeated or re-encoded. A slower live browser can miss a
    bucket; offline comparison intentionally includes all bucket starts.
    """
    if not math.isfinite(source_fps) or source_fps <= 0:
        raise ValueError('source_fps must be positive')
    previous_bucket = -1
    for frame_id, frame in enumerate(frames):
        time_s = frame_id / source_fps
        bucket = math.floor(time_s * target_fps + 1e-8)
        if bucket > previous_bucket:
            previous_bucket = bucket
            yield frame_id, time_s, frame


def load_source(path: str) -> tuple[cv2.VideoCapture, float]:
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise OSError(f'Cannot open input video: {path}')
    source_fps = float(cap.get(cv2.CAP_PROP_FPS))
    if not 1 <= source_fps <= 240:
        cap.release()
        raise ValueError('Original source frame rate unavailable; cannot make an exact comparison')
    return cap, source_fps


def read_frames(cap: cv2.VideoCapture) -> Iterator[np.ndarray]:
    while True:
        ok, frame = cap.read()
        if not ok:
            return
        yield frame


def collect_reference(frames: Iterable[np.ndarray], fps: float, calib: Calibration,
                      config: DemoConfig) -> list[dict]:
    """The *same* actual source video frames feed full-rate and 8-FPS paths."""
    original: WaterDetector | None = None
    previous_bucket = -1
    samples: list[dict] = []
    for frame_id, frame in enumerate(frames):
        if original is None:
            original = WaterDetector(frame.shape[:2], fps, calib, config)
        full_result = original.process(frame)
        time_s = frame_id / fps
        bucket = math.floor(time_s * SAMPLE_FPS + 1e-8)
        if bucket <= previous_bucket:
            continue
        previous_bucket = bucket
        # The source frame is retained losslessly in memory for candidate runs.
        samples.append({
            'frame_id': frame_id,
            'time_s': time_s,
            'frame': frame.copy(),
            'original_s_water': float(full_result['s_water']),
            'original_status': full_result['status'],
            'original_ready': bool(full_result['history_ready']),
        })
    return samples


def run_candidate(samples: list[dict], calib: Calibration,
                  config: DemoConfig) -> list[dict]:
    if not samples:
        raise ValueError('No video frames supplied')
    h, w = samples[0]['frame'].shape[:2]
    detector = WaterDetector((h, w), SAMPLE_FPS, calib, config)
    output = []
    last_s = None
    for packet in samples:
        t = packet['time_s']
        # The live backend reinitializes its history on large video-time gaps.
        if last_s is not None and (t <= last_s or t-last_s > 1.6 / SAMPLE_FPS):
            detector = WaterDetector((h, w), SAMPLE_FPS, calib, config)
        last_s = t
        result = detector.process(packet['frame'])
        output.append({
            'frame_id': packet['frame_id'],
            'time_s': t,
            'original_s_water': packet['original_s_water'],
            'original_status': packet['original_status'],
            'original_ready': packet['original_ready'],
            'sampled_s_water': float(result['s_water']),
            'sampled_status': result['status'],
            'sampled_ready': bool(result['history_ready']),
        })
    return output


def score_comparison(comparison: list[dict]) -> dict:
    valid = [x for x in comparison if x['original_ready'] and x['sampled_ready']]
    if not valid:
        return {'score': float('inf'), 'mae': float('inf'),
                'status_agreement': 0, 'compared_frames': 0}
    mae = sum(abs(x['original_s_water'] - x['sampled_s_water']) for x in valid) / len(valid)
    agree = sum(x['original_status'] == x['sampled_status'] for x in valid) / len(valid)
    # Keep original OK/NG behavior relevant without replacing the original
    # thresholds. Tune only frame-difference and persistence parameters.
    return {
        'score': round(mae + .05 * (1 - agree), 8),
        'mae': round(mae, 8),
        'status_agreement': round(agree, 5),
        'compared_frames': len(valid),
    }


def tune_candidates(samples: list[dict], calib: Calibration,
                    original_settings: DemoConfig, full_search: bool = False) -> list[dict]:
    diffs = [8.0, 12.0, 16.0, 24.0] if not full_search else [8.0, 10.0, 12.0, 16.0, 24.0, 32.0]
    histories = [.5, .625] if not full_search else [.375, .5, .625, .75]
    persistences = [.5, .75] if not full_search else [.5, .625, .75, .875]
    candidates = []
    # Always score the unchanged original first, even if user provided
    # additional settings that aren't represented in the grid.
    grids = [(original_settings.diff_threshold, original_settings.history_seconds,
              original_settings.persistence_threshold)]
    grids += [(d, h, p) for d in diffs for h in histories for p in persistences]
    seen = set()
    for diff, history, persistence in grids:
        key = (diff, history, persistence)
        if key in seen:
            continue
        seen.add(key)
        cfg = replace(original_settings, diff_threshold=diff,
                      history_seconds=history, persistence_threshold=persistence)
        metrics = score_comparison(run_candidate(samples, calib, cfg))
        candidates.append({'diff_threshold': diff, 'history_seconds': history,
                           'persistence_threshold': persistence, **metrics})
    return sorted(candidates, key=lambda x: (x['score'], x['mae'], x['diff_threshold']))


def write_comparison_csv(path: str | Path, values: list[dict]) -> None:
    if not values:
        return
    columns = [x for x in values[0] if x != 'frame']
    with open(path, 'w', newline='', encoding='utf-8-sig') as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in values:
            writer.writerow({key: row[key] for key in columns})


def comparison_report(path: str, calib: Calibration, output_csv: str,
                      output_json: str, full_search: bool = False) -> dict:
    cap, fps = load_source(path)
    try:
        original_settings = DemoConfig()
        samples = collect_reference(read_frames(cap), fps, calib, original_settings)
        if len(samples) < 8:
            raise ValueError('Video is too short to compare temporal windows')
        baseline = run_candidate(samples, calib, original_settings)
        rankings = tune_candidates(samples, calib, original_settings, full_search)
        best = rankings[0]
        candidate = replace(original_settings, **{key: best[key] for key in TUNED_KEYS})
        report = {
            'video': str(Path(path).resolve()), 'source_fps': fps,
            'analysis_fps': SAMPLE_FPS, 'selected_frames': len(samples),
            'input_preprocessing': 'same OpenCV-decoded BGR frames, no JPEG',
            'baseline': score_comparison(baseline),
            'best_fit': best,
            'candidate_algorithm_settings': {k: asdict(candidate)[k] for k in EDITABLE_KEYS},
            'status': 'UNVALIDATED_CANDIDATE',
            'warning': 'Do not apply automatically: compare independent good AND bad videos first.',
            'top_candidates': rankings[:10],
        }
        write_comparison_csv(output_csv, baseline)
        Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        return report
    finally:
        cap.release()
