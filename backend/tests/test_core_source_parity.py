"""Guard canonical algorithm parity with the user-uploaded main1_chn.py.

Hashes were computed from the AST of the uploaded file's DemoConfig,
Calibration and WaterDetector classes. This covers all executable statements,
defaults and method bodies, independent of formatting or comments.
"""
from __future__ import annotations

import ast
import base64
import hashlib
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

from sample_backend.main import create_app
from sample_backend.services.water_detection import Calibration, DemoConfig, WaterDetector

SOURCE_SHA256 = {
    'DemoConfig': 'f422b062236a899b7dfd0cfcfd809f4fa545edd332f099e84f47059d0ae17e85',
    'Calibration': '3bb83270ccd1bb7e6fe4008dc1061ea37a5122d08a749cb380641df001304fcf',
    'WaterDetector': '4c588e7f0b0d552c57fbdcd91f15a56edb2c954904901e52b78386afe45ca144',
}


def test_core_matches_uploaded_main1_chn_py_ast_exactly():
    path = (Path(__file__).resolve().parents[1]
            / 'src' / 'sample_backend' / 'services' / 'water_detection.py')
    tree = ast.parse(path.read_text(encoding='utf-8'))
    classes = {
        node.name: node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name in SOURCE_SHA256
    }
    assert set(classes) == set(SOURCE_SHA256)
    for name, expected in SOURCE_SHA256.items():
        canonical = ast.dump(classes[name], annotate_fields=True, include_attributes=False)
        sha = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
        assert sha == expected, f'{name} differs from uploaded main1_chn.py: {sha}'


def test_http_api_equals_direct_water_detector_on_same_frames_even_with_gaps():
    """No transport-level logic may alter S_water, sectors, or OK/NG state."""
    direct = WaterDetector((96, 96), 8.0, Calibration(48, 48, 32), DemoConfig())
    times = [i / 8 for i in range(12)] + [2.25 + i / 8 for i in range(10)]
    with TestClient(create_app()) as client:
        start = client.post('/api/detection/start', json={
            'sample_fps': 8,
            'calibration': {'cx': 48, 'cy': 48, 'radius': 32,
                            'width': 96, 'height': 96},
        })
        assert start.status_code == 200, start.text
        sid = start.json()['session_id']

        for i, time_s in enumerate(times):
            rng = np.random.default_rng(i + 32)
            frame = np.full((96, 96, 3), 90, dtype=np.uint8)
            yy, xx = np.indices((96, 96))
            ring = (((xx - 48) ** 2 + (yy - 48) ** 2 >= 22 ** 2)
                    & ((xx - 48) ** 2 + (yy - 48) ** 2 <= 30 ** 2))
            frame[ring] = rng.integers(40, 140, size=(int(ring.sum()), 1), dtype=np.uint8)
            success, encoded = cv2.imencode('.png', frame)
            assert success
            restored = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
            assert np.array_equal(frame, restored)
            api = client.post('/api/detection/frame', json={
                'session_id': sid,
                'time_s': time_s,
                'png_base64': base64.b64encode(encoded).decode('ascii'),
            })
            assert api.status_code == 200, api.text
            actual = api.json()
            expected = direct.process(frame)
            for key in ('status', 'history_ready', 'max_sector_idx',
                        's_water', 'max_sector_score', 'abnormal_run_s'):
                assert actual[key] == expected[key], (time_s, key)
            assert actual['sector_scores'] == expected['sector_scores']


def test_bad_timestamp_is_rejected_without_modifying_detector_state():
    with TestClient(create_app()) as client:
        start = client.post('/api/detection/start', json={
            'sample_fps': 8,
            'calibration': {'cx': 48, 'cy': 48, 'radius': 32,
                            'width': 96, 'height': 96},
        })
        assert start.status_code == 200
        sid = start.json()['session_id']
        image = np.full((96, 96, 3), 90, dtype=np.uint8)
        ok, encoded = cv2.imencode('.png', image)
        assert ok
        packet = {'session_id': sid,
                  'png_base64': base64.b64encode(encoded).decode('ascii')}
        assert client.post('/api/detection/frame', json={
            **packet, 'time_s': 1.0,
        }).status_code == 200
        for time_s in (1.0, .875):
            assert client.post('/api/detection/frame', json={
                **packet, 'time_s': time_s,
            }).status_code == 422
        assert client.post('/api/detection/frame', json={
            **packet, 'time_s': 1.125,
        }).status_code == 200
