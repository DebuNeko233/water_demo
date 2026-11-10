"""Start/stop must release video resources and reject stale session IDs."""
import time

import cv2
import numpy as np
from fastapi.testclient import TestClient

from sample_backend.main import create_app
from sample_backend.services import video_stream


CALIBRATION = {
    'cx': 48, 'cy': 48, 'radius': 32,
    'width': 96, 'height': 96,
}


def make_file(tmp_path):
    path = tmp_path / 'stop.avi'
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 25, (96, 96))
    assert writer.isOpened()
    for i in range(12):
        writer.write(np.full((96, 96, 3), 40 + i * 3, dtype=np.uint8))
    writer.release()
    return path


def test_stop_releases_file_capture_and_rejects_stale_session(tmp_path):
    video = make_file(tmp_path)
    with TestClient(create_app()) as client:
        request = {'calibration': CALIBRATION, 'file_path': str(video)}
        opened = client.post('/api/video/open', json=request)
        assert opened.status_code == 200, opened.text
        first_sid = opened.json()['session_id']
        capture = client.app.state.video_stream._cap
        assert capture is not None and capture.isOpened()

        denied = client.post('/api/video/stop', json={'session_id': 'other-session'})
        assert denied.status_code == 409
        assert capture.isOpened()
        assert client.post('/api/video/next', json={
            'session_id': first_sid,
        }).status_code == 200

        stopped = client.post('/api/video/stop', json={'session_id': first_sid})
        assert stopped.status_code == 200, stopped.text
        assert stopped.json() == {'stopped': True}
        assert not capture.isOpened()
        assert client.app.state.video_stream._cap is None
        assert client.post('/api/video/next', json={
            'session_id': first_sid,
        }).status_code == 409
        assert client.post('/api/video/stop', json={
            'session_id': first_sid,
        }).status_code == 409

        second = client.post('/api/video/open', json=request)
        assert second.status_code == 200, second.text
        new_sid = second.json()['session_id']
        assert new_sid != first_sid
        assert client.post('/api/video/stop', json={
            'session_id': first_sid,
        }).status_code == 409
        assert client.post('/api/video/next', json={
            'session_id': new_sid,
        }).status_code == 200


class FakeCamera:
    def __init__(self):
        self.count = 0
        self.opened = True

    def isOpened(self):
        return self.opened

    def get(self, prop):
        return {
            cv2.CAP_PROP_FRAME_WIDTH: 96,
            cv2.CAP_PROP_FRAME_HEIGHT: 96,
            cv2.CAP_PROP_FPS: 24,
            cv2.CAP_PROP_FRAME_COUNT: 0,
        }.get(prop, 0)

    def read(self):
        if not self.opened:
            return False, None
        self.count += 1
        return True, np.full((96, 96, 3), 120, dtype=np.uint8)

    def set(self, prop, value):
        return True

    def release(self):
        self.opened = False


def test_stop_releases_live_camera_and_terminates_worker(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_DATA_DIR', str(tmp_path / 'data'))
    cameras = []
    def fake_open(source, file_path=''):
        assert source.kind == 'usb'
        cam = FakeCamera()
        cameras.append(cam)
        return cam
    monkeypatch.setattr(video_stream, 'open_capture', fake_open)
    with TestClient(create_app()) as client:
        setup = client.post('/api/users/setup', json={'password': 'StopTest#742'})
        assert setup.status_code == 200, setup.text
        token = setup.json()['admin_token']
        assert client.post('/api/video/source/save', json={
            'admin_token': token, 'source': {'kind': 'usb', 'usb_index': 1},
        }).status_code == 200
        opened = client.post('/api/video/open', json={'calibration': CALIBRATION})
        assert opened.status_code == 200, opened.text
        sid = opened.json()['session_id']
        assert cameras[0].opened

        stopped = client.post('/api/video/stop', json={'session_id': sid})
        assert stopped.status_code == 200, stopped.text
        assert not cameras[0].opened
        count = cameras[0].count
        time.sleep(0.09)
        assert cameras[0].count == count
        assert client.post('/api/video/next', json={
            'session_id': sid,
        }).status_code == 409
        restarted = client.post('/api/video/open', json={'calibration': CALIBRATION})
        assert restarted.status_code == 200
        assert len(cameras) == 2
        assert cameras[1].opened
