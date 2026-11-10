"""The monitor's video playback and water inference are separate controls."""
from __future__ import annotations

import time

import cv2
import numpy as np
from fastapi.testclient import TestClient

from sample_backend.main import create_app
from sample_backend.services import video_stream
from sample_backend.services.water_detection import Calibration, DemoConfig, WaterDetector


CAL = {'cx': 48, 'cy': 48, 'radius': 32, 'width': 96, 'height': 96}


def make_video(tmp_path, count=16):
    path = tmp_path / 'preview_only.avi'
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'),
                             25, (96, 96))
    assert writer.isOpened()
    for i in range(count):
        rng = np.random.default_rng(i)
        writer.write(rng.integers(20, 220, size=(96, 96, 3), dtype=np.uint8))
    writer.release()
    return path


def test_file_preview_plays_without_inference_and_resume_does_not_seek(tmp_path):
    path = make_video(tmp_path)
    with TestClient(create_app()) as client:
        opened = client.post('/api/video/open', json={
            'file_path': str(path), 'calibration': CAL,
            'detecting': False,
        })
        assert opened.status_code == 200, opened.text
        response = opened.json()
        sid = response['session_id']
        assert response['detecting'] is False
        assert response['frame']['detecting'] is False
        assert response['frame']['result']['reason'] == 'DETECTION_STOPPED'
        assert response['frame']['jpeg_base64']

        packet = client.post('/api/video/next', json={
            'session_id': sid, 'batch_frames': 3,
        }).json()
        assert packet['frame_index'] == 3
        assert packet['detecting'] is False
        assert all(row['status'] == 'PAUSED' for row in packet['samples'])
        assert packet['result']['s_water'] == 0.0
        assert client.app.state.video_stream._detector._inner.prev_gray is None

        enabled = client.post('/api/video/detection/start', json={'session_id': sid})
        assert enabled.status_code == 200
        assert enabled.json() == {'detecting': True}
        next_frame = client.post('/api/video/next', json={
            'session_id': sid,
        }).json()
        assert next_frame['frame_index'] == 4
        assert next_frame['detecting'] is True
        assert next_frame['result']['status'] == 'WARMUP'
        assert next_frame['result']['history_ready'] is False

        disabled = client.post('/api/video/detection/stop', json={'session_id': sid})
        assert disabled.status_code == 200
        assert disabled.json() == {'detecting': False}
        cap = client.app.state.video_stream._cap
        assert cap is not None and cap.isOpened()
        still_playing = client.post('/api/video/next', json={
            'session_id': sid,
        }).json()
        assert still_playing['frame_index'] == 5
        assert still_playing['detecting'] is False
        assert still_playing['result']['reason'] == 'DETECTION_STOPPED'

        # A second start resets the history and does not rewind the video.
        assert client.post('/api/video/detection/start', json={
            'session_id': sid,
        }).status_code == 200
        resumed = client.post('/api/video/next', json={
            'session_id': sid,
        }).json()
        assert resumed['frame_index'] == 6
        assert resumed['result']['status'] == 'WARMUP'
        assert resumed['result']['history_ready'] is False
        assert cap.isOpened()
        for endpoint in ['/api/video/detection/start', '/api/video/detection/stop']:
            assert client.post(endpoint, json={
                'session_id': 'stale',
            }).status_code == 409


class Camera:
    def __init__(self):
        self.opened = True
        self.count = 0

    def isOpened(self):
        return self.opened

    def get(self, key):
        return {
            cv2.CAP_PROP_FRAME_WIDTH: 96,
            cv2.CAP_PROP_FRAME_HEIGHT: 96,
            cv2.CAP_PROP_FPS: 25,
            cv2.CAP_PROP_FRAME_COUNT: 0,
        }.get(key, 0)

    def read(self):
        if not self.opened:
            return False, None
        self.count += 1
        return True, np.full((96, 96, 3), 100, np.uint8)

    def set(self, key, value):
        return True

    def release(self):
        self.opened = False


def test_live_camera_keeps_acquiring_while_detection_switches(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_DATA_DIR', str(tmp_path / 'data'))
    camera = Camera()
    monkeypatch.setattr(video_stream, 'open_capture',
                        lambda source, file_path='': camera)
    with TestClient(create_app()) as client:
        setup = client.post('/api/users/setup', json={'password': 'ValidPass123!'})
        assert setup.status_code == 200, setup.text
        token = setup.json()['admin_token']
        saved = client.post('/api/video/source/save', json={
            'admin_token': token, 'source': {'kind': 'usb', 'usb_index': 1},
        })
        assert saved.status_code == 200, saved.text
        opened = client.post('/api/video/open', json={
            'calibration': CAL, 'detecting': False,
        })
        assert opened.status_code == 200, opened.text
        sid = opened.json()['session_id']
        assert camera.opened and camera.count >= 1
        before = camera.count
        time.sleep(0.14)  # Simulates pausing the displayed image.
        assert camera.count > before
        assert client.post('/api/video/detection/start', json={
            'session_id': sid,
        }).json() == {'detecting': True}
        time.sleep(0.11)
        packet = client.post('/api/video/next', json={
            'session_id': sid,
        }).json()
        assert packet['detecting'] is True
        assert packet['result']['reason'] != 'DETECTION_STOPPED'
        assert client.post('/api/video/detection/stop', json={
            'session_id': sid,
        }).json() == {'detecting': False}
        count = camera.count
        time.sleep(0.13)
        assert camera.opened and camera.count > count
        packet = client.post('/api/video/next', json={
            'session_id': sid,
        }).json()
        assert packet['detecting'] is False
        assert packet['result']['reason'] == 'DETECTION_STOPPED'
        closed = client.post('/api/video/stop', json={'session_id': sid})
        assert closed.status_code == 200
        assert not camera.opened
