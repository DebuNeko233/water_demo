"""Full-FPS Python-owned video decoder and atomic image/result packet regression."""
import base64

import cv2
import numpy as np
from fastapi.testclient import TestClient

from sample_backend.main import create_app
from sample_backend.services.water_detection import Calibration, DemoConfig, WaterDetector


def create_video(tmp_path, fps=30, count=24):
    path = tmp_path / 'source.mp4'
    writer = cv2.VideoWriter(str(path),
                             cv2.VideoWriter_fourcc(*'mp4v'), fps, (96, 96))
    assert writer.isOpened()
    yy, xx = np.indices((96, 96))
    ring = ((xx - 48) ** 2 + (yy - 48) ** 2 >= 21 ** 2) & (
        (xx - 48) ** 2 + (yy - 48) ** 2 <= 31 ** 2)
    for i in range(count):
        img = np.full((96, 96, 3), 95, dtype=np.uint8)
        rng = np.random.default_rng(i)
        img[ring] = rng.integers(35, 145, size=(int(ring.sum()), 1), dtype=np.uint8)
        writer.write(img)
    writer.release()
    return path


def request_open(client, path, start=0):
    return client.post('/api/video/open', json={
        'file_path': str(path),
        'start_time_s': start,
        'calibration': {
            'cx': 48, 'cy': 48, 'radius': 34, 'width': 96, 'height': 96,
        },
    })


def test_python_decodes_every_original_frame_and_returns_exact_detector_results(tmp_path):
    video = create_video(tmp_path)
    cap = cv2.VideoCapture(str(video))
    assert cap.isOpened()
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    direct = WaterDetector((96, 96), fps,
                           Calibration(48, 48, 34), DemoConfig())
    with TestClient(create_app()) as client:
        opened = request_open(client, video)
        assert opened.status_code == 200, opened.text
        data = opened.json()
        sid = data['session_id']
        assert abs(data['fps'] - 30) < 1e-3
        assert data['width'] == 96 and data['height'] == 96
        assert abs(data['duration_s'] - 24 / fps) < 1e-2
        assert data['frame']['frame_index'] == 0
        assert data['frame_count'] == 24

        for i in range(24):
            packet = data['frame'] if i == 0 else client.post('/api/video/next', json={
                'session_id': sid,
            }).json()
            assert not packet['ended']
            assert packet['frame_index'] == i
            assert abs(packet['time_s'] - i / fps) < 1e-7
            ok, decoded = cap.read()
            assert ok
            truth = direct.process(decoded)
            actual = packet['result']
            for key in ('status', 's_water', 'history_ready',
                        'max_sector_idx', 'max_sector_score',
                        'sector_scores', 'abnormal_run_s'):
                assert actual[key] == truth[key], (i, key, actual[key], truth[key])
            assert actual['time_s'] == packet['time_s']
            # Display frame has ring/sector overlays and can be JPEG, but this
            # encoding happens only AFTER original BGR frame is analyzed.
            preview = cv2.imdecode(
                np.frombuffer(base64.b64decode(packet['jpeg_base64']), np.uint8),
                cv2.IMREAD_COLOR)
            assert preview.shape == (96, 96, 3)
            assert not np.array_equal(preview, decoded)

        last = client.post('/api/video/next', json={'session_id': sid})
        assert last.status_code == 200
        assert last.json() == {'ended': True}
    cap.release()


def test_pause_is_naturally_backpressured_and_seek_restarts_at_exact_frame(tmp_path):
    video = create_video(tmp_path)
    with TestClient(create_app()) as client:
        opened = request_open(client, video).json()
        sid = opened['session_id']
        assert opened['frame']['frame_index'] == 0
        # Pausing means the frontend stops requesting frames. The VideoCapture
        # does NOT advance in a background thread while paused.
        next_packet = client.post('/api/video/next', json={'session_id': sid}).json()
        assert next_packet['frame_index'] == 1

        seeked = client.post('/api/video/seek', json={
            'session_id': sid, 'time_s': 10 / 30,
        })
        assert seeked.status_code == 200, seeked.text
        packet = seeked.json()
        assert packet['frame_index'] == 10
        assert packet['result']['status'] == 'WARMUP'
        after = client.post('/api/video/next', json={'session_id': sid}).json()
        assert after['frame_index'] == 11
        assert after['result']['history_ready'] is False

        replaced = request_open(client, video).json()
        stale = client.post('/api/video/next', json={'session_id': sid})
        assert replaced['session_id'] != sid
        assert stale.status_code == 409


def test_rejects_missing_file_and_wrong_calibration_before_start(tmp_path):
    with TestClient(create_app()) as client:
        assert request_open(client, tmp_path / 'missing.mp4').status_code == 422
        video = create_video(tmp_path, count=4)
        invalid = client.post('/api/video/open', json={
            'file_path': str(video),
            'calibration': {
                'cx': 48, 'cy': 48, 'radius': 34, 'width': 720, 'height': 576,
            },
        })
        assert invalid.status_code == 422
        assert invalid.json()['detail'] == {
            'code': 'CALIBRATION_RESOLUTION_MISMATCH',
            'video_width': 96, 'video_height': 96,
            'calibration_width': 720, 'calibration_height': 576,
        }


def test_oversize_video_is_distinguished_from_mismatched_roi(monkeypatch):
    from sample_backend.services import video_stream

    class MetadataOnlyCapture:
        released = False

        def isOpened(self):
            return True

        def get(self, prop):
            return {
                cv2.CAP_PROP_FRAME_WIDTH: 3840,
                cv2.CAP_PROP_FRAME_HEIGHT: 2160,
                cv2.CAP_PROP_FPS: 30,
                cv2.CAP_PROP_FRAME_COUNT: 80,
            }.get(prop, 0)

        def release(self):
            self.released = True

    capture = MetadataOnlyCapture()
    monkeypatch.setattr(video_stream, 'open_capture', lambda source, file_path='': capture)
    with TestClient(create_app()) as client:
        response = client.post('/api/video/open', json={
            'calibration': {'cx': 400, 'cy': 400, 'radius': 200,
                            'width': 3840, 'height': 2160},
        })
        assert response.status_code == 422
        assert response.json()['detail'] == {
            'code': 'VIDEO_RESOLUTION_TOO_LARGE',
            'video_width': 3840, 'video_height': 2160,
        }
    assert capture.released
