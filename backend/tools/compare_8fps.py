#!/usr/bin/env python3
"""Compare the original full-FPS water detector with lossless 8-FPS sampling.

Example (run from repository root):
uv run --project backend python backend/tools/compare_8fps.py \
  --video good.mp4 --cx 264 --cy 443 --radius 108 \
  --comparison-csv compare-good.csv --report-json compare-good.json

Repeat with a known-NG recording BEFORE applying a fitted parameter profile.
"""
from __future__ import annotations

import argparse
import json

from sample_backend.services.water_detection import Calibration
from sample_backend.services.reference_comparison import comparison_report


def main() -> None:
    parser = argparse.ArgumentParser(description='Reproducible 30 FPS vs 8 FPS WaterDetector comparison')
    parser.add_argument('--video', required=True)
    parser.add_argument('--cx', required=True, type=float)
    parser.add_argument('--cy', required=True, type=float)
    parser.add_argument('--radius', required=True, type=float)
    parser.add_argument('--comparison-csv', default='comparison-8fps.csv')
    parser.add_argument('--report-json', default='calibration-8fps.json')
    parser.add_argument('--full-search', action='store_true',
                        help='Explore a wider parameter grid (slower)')
    args = parser.parse_args()
    result = comparison_report(args.video,
        Calibration(args.cx, args.cy, args.radius),
        args.comparison_csv, args.report_json, args.full_search)
    print(json.dumps({
        'input_fps': result['source_fps'],
        'sampled_frames': result['selected_frames'],
        'original_settings_score': result['baseline'],
        'preliminary_best_candidate': result['best_fit'],
        'warning': result['warning'],
        'comparison_csv': args.comparison_csv,
        'report_json': args.report_json,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
