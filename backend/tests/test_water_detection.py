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

def test_custom_algorithm_settings_apply_to_detector_and_reinitialize_history():
    custom = dict(inner_radius_ratio=0.55, outer_radius_ratio=0.98,
                  diff_threshold=11.0, history_seconds=0.375,
                  persistence_threshold=0.6, s_water_threshold=0.09,
                  ng_hold_seconds=0.75, recover_hold_seconds=0.9,
                  sector_count=12, sector_threshold=0.08, blur_ksize=5)
    with TestClient(create_app()) as client:
        payload = {'sample_fps': 8, 'calibration': {
            'cx': 48, 'cy': 48, 'radius': 32, 'width': 96, 'height': 96},
            'detector': custom}
        response = client.post('/api/detection/start', json=payload)
        assert response.status_code == 200, response.text
        started = response.json()
        assert started['sector_count'] == 12
        assert started['s_water_threshold'] == 0.09
        assert started['inner_radius_ratio'] == 0.55
        assert started['outer_radius_ratio'] == 0.98
        first = client.post('/api/detection/frame', json={
            'session_id': started['session_id'],
            'time_s': 1, 'jpeg_base64': make_jpeg(1)})
        assert first.status_code == 200
        state = first.json()
        assert state['status'] == 'WARMUP'
        assert state['sector_count'] == 12
        assert len(state['sector_scores']) == 12
        assert state['s_water_threshold'] == 0.09
        assert state['sector_threshold'] == 0.08
        # New settings => new session, old one must not continue.
        payload['detector']['sector_count'] = 16
        second = client.post('/api/detection/start', json=payload).json()
        assert second['session_id'] != started['session_id']
        assert second['sector_count'] == 16
        assert client.post('/api/detection/frame', json={
            'session_id': started['session_id'], 'time_s': 1.125,
            'jpeg_base64': make_jpeg(2)}).status_code == 409


def test_invalid_algorithm_settings_are_rejected_before_detection_start():
    with TestClient(create_app()) as client:
        base = {'sample_fps': 8, 'calibration': {
            'cx': 48, 'cy': 48, 'radius': 32, 'width': 96, 'height': 96}}
        for bad in [
            {'inner_radius_ratio': 0.95, 'outer_radius_ratio': 0.65},
            {'blur_ksize': 4},
            {'history_seconds': 5},
            {'sector_count': 0},
            {'s_water_threshold': -0.1},
        ]:
            r = client.post('/api/detection/start', json={**base, 'detector': bad})
            assert r.status_code == 422, (bad, r.text)
        assert client.post('/api/detection/start', json=base).status_code == 200


def test_default_parameters_match_original_main1_chn_demo_config():
    """The API defaults must not drift from the source detector defaults."""
    from sample_backend.services.water_detection import DemoConfig
    from sample_backend.services.water_session import DetectorSettings

    defaults = DetectorSettings().model_dump()
    original = DemoConfig()
    assert defaults == {key: getattr(original, key) for key in defaults}
    assert defaults == {
        "inner_radius_ratio": 0.65,
        "outer_radius_ratio": 0.95,
        "diff_threshold": 8.0,
        "history_seconds": 0.50,
        "persistence_threshold": 0.50,
        "s_water_threshold": 0.025,
        "ng_hold_seconds": 0.50,
        "recover_hold_seconds": 0.60,
        "sector_count": 24,
        "sector_threshold": 0.05,
        "blur_ksize": 3,
    }


def test_lossless_png_transport_preserves_detector_inputs_and_rejects_fake_png():
    with TestClient(create_app()) as client:
        session = begin(client)
        rng = np.random.default_rng(123)
        frame = rng.integers(0, 256, size=(96, 96, 3), dtype=np.uint8)
        ok, encoded = cv2.imencode('.png', frame)
        assert ok
        # Unlike JPEG, OpenCV re-decoding must preserve the original BGR pixels.
        restored = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        assert np.array_equal(restored, frame)
        response = client.post('/api/detection/frame', json={
            'session_id': session, 'time_s': 0,
            'png_base64': base64.b64encode(encoded.tobytes()).decode('ascii'),
        })
        assert response.status_code == 200, response.text
        assert response.json()['status'] == 'WARMUP'
        fake = client.post('/api/detection/frame', json={
            'session_id': session, 'time_s': 0.125,
            'png_base64': base64.b64encode(b'not PNG').decode('ascii'),
        })
        assert fake.status_code == 422
        both = client.post('/api/detection/frame', json={
            'session_id': session, 'time_s': 0.25,
            'png_base64': base64.b64encode(encoded.tobytes()).decode('ascii'),
            'jpeg_base64': make_jpeg(),
        })
        assert both.status_code == 422


def test_lossless_png_sequence_reaches_real_detector_state():
    with TestClient(create_app()) as client:
        session = begin(client)
        scores = []
        for i in range(12):
            frame = np.full((96, 96, 3), 80, dtype=np.uint8)
            yy, xx = np.indices((96, 96))
            ring = ((xx - 48) ** 2 + (yy - 48) ** 2 >= 22 ** 2) & (
                (xx - 48) ** 2 + (yy - 48) ** 2 <= 30 ** 2)
            rng = np.random.default_rng(i)
            frame[ring] = rng.integers(30, 150, size=(ring.sum(), 1), dtype=np.uint8)
            ok, buf = cv2.imencode('.png', frame)
            assert ok
            response = client.post('/api/detection/frame', json={
                'session_id': session, 'time_s': i / 8,
                'png_base64': base64.b64encode(buf.tobytes()).decode('ascii'),
            })
            assert response.status_code == 200, response.text
            scores.append(response.json()['s_water'])
        assert max(scores) > 0


def test_missing_analyzed_video_time_bucket_resets_instead_of_faking_consecutive_frames():
    # At a target rate of 8 FPS, a 0.375 s gap means multiple 8 Hz
    # sampling buckets were skipped. The original algorithm assumes
    # consecutive samples: temporal statistics must be restarted.
    with TestClient(create_app()) as client:
        sid = begin(client)
        for i in range(7):
            response = client.post('/api/detection/frame', json={
                'session_id': sid, 'time_s': i / 8,
                'jpeg_base64': make_jpeg(i),
            })
            assert response.status_code == 200
        after_gap = client.post('/api/detection/frame', json={
            'session_id': sid, 'time_s': 1.125,
            'jpeg_base64': make_jpeg(99),
        })
        assert after_gap.status_code == 200
        assert after_gap.json()['status'] == 'WARMUP'
        assert len(after_gap.json()['history']) == 1
