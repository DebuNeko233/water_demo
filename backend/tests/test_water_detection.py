"""Integration tests against the real original detector and HTTP frame bridge."""
import base64
import math
import cv2
import numpy as np
from fastapi.testclient import TestClient
from sample_backend.main import create_app


def make_jpeg(noise_seed=None):
    im = np.full((96, 96, 3), 90, dtype=np.uint8)
    if noise_seed is not None:
        rng = np.random.default_rng(noise_seed)
        yy, xx = np.mgrid[:96, :96]
        annulus = ((xx - 48) ** 2 + (yy - 48) ** 2 >= 22 ** 2) & (
            (xx - 48) ** 2 + (yy - 48) ** 2 <= 30 ** 2)
        # Localized moving noise, not global brightness change.
        im[annulus] = rng.integers(50, 140, size=(int(annulus.sum()), 1), dtype=np.uint8)
    ok, encoded = cv2.imencode('.jpg', im)
    assert ok
    return base64.b64encode(encoded.tobytes()).decode()


def begin(client):
    res = client.post('/api/detection/start', json={
        'sample_fps': 8,
        'calibration': {'cx': 48, 'cy': 48, 'radius': 32, 'width': 96, 'height': 96},
    })
    assert res.status_code == 200, res.text
    data = res.json()
    assert data['s_water_threshold'] == 0.025
    assert data['sector_count'] == 24
    return data['session_id']


def test_detector_refreshes_scores_status_sectors_history():
    with TestClient(create_app()) as client:
        sid = begin(client)
        outputs = []
        for i in range(14):
            r = client.post('/api/detection/frame', json={
                'session_id': sid, 'time_s': i / 8,
                'jpeg_base64': make_jpeg(i),
            })
            assert r.status_code == 200, r.text
            outputs.append(r.json())
        assert outputs[0]['status'] == 'WARMUP'
        assert any(o['history_ready'] for o in outputs)
        assert any(o['s_water'] > 0.025 for o in outputs)
        assert any(o['status'] == 'NG' for o in outputs)
        last = outputs[-1]
        assert len(last['sector_scores']) == 24
        assert last['max_sector_idx'] >= 0
        assert last['max_sector_score'] > 0
        assert len(last['history']) == 14
        assert last['history'][-1]['time_s'] == 13 / 8


def test_reset_and_malformed_video_frame():
    with TestClient(create_app()) as client:
        a = begin(client)
        r = client.post('/api/detection/frame', json={
            'session_id': a, 'time_s': 1, 'jpeg_base64': 'not_base64!',
        })
        assert r.status_code == 422
        bad_shape = np.zeros((80, 80, 3), dtype=np.uint8)
        ok, jpeg = cv2.imencode('.jpg', bad_shape)
        assert ok
        r = client.post('/api/detection/frame', json={
            'session_id': a, 'time_s': 1, 'jpeg_base64': base64.b64encode(jpeg).decode(),
        })
        assert r.status_code == 422
        b = begin(client)
        assert a != b
        r = client.post('/api/detection/frame', json={
            'session_id': a, 'time_s': 0, 'jpeg_base64': make_jpeg(3),
        })
        assert r.status_code == 409
        r = client.post('/api/detection/frame', json={
            'session_id': b, 'time_s': 0, 'jpeg_base64': make_jpeg(3),
        })
        assert r.status_code == 200
        assert r.json()['status'] == 'WARMUP'


def test_time_jump_resets_temporal_history():
    with TestClient(create_app()) as client:
        sid = begin(client)
        for i in range(8):
            client.post('/api/detection/frame', json={
                'session_id': sid, 'time_s': i / 8, 'jpeg_base64': make_jpeg(i),
            })
        res = client.post('/api/detection/frame', json={
            'session_id': sid, 'time_s': 4.0, 'jpeg_base64': make_jpeg(22),
        })
        assert res.status_code == 200
        assert res.json()['status'] == 'WARMUP'
        assert len(res.json()['history']) == 1