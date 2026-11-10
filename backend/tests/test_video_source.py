"""Configured file/RTSP/USB source authorization and live camera regression."""
import time

import cv2
import numpy as np
from fastapi.testclient import TestClient

from sample_backend.main import create_app
from sample_backend.services import video_stream


def admin(client):
    result = client.post('/api/users/setup', json={'password': 'Camera#test742'})
    assert result.status_code == 200, result.text
    return result.json()['admin_token']


def test_source_config_requires_admin_and_persists_without_exposing_rtsp_password(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_DATA_DIR', str(tmp_path / 'data'))
    with TestClient(create_app()) as client:
        assert client.get('/api/video/source').json() == {'kind': 'file', 'usb_index': 0}
        blocked = client.post('/api/video/source/save', json={
            'admin_token': 'invalid', 'source': {'kind': 'usb', 'usb_index': 2},
        })
        assert blocked.status_code == 403
        token = admin(client)
        value = {'kind': 'rtsp', 'rtsp_url': 'rtsp://admin:super-secret@127.0.0.1:8554/live',
                 'usb_index': 0}
        saved = client.post('/api/video/source/save', json={
            'admin_token': token, 'source': value,
        })
        assert saved.status_code == 200, saved.text
        public = client.get('/api/video/source').json()
        assert public['kind'] == 'rtsp'
        assert 'rtsp_url' not in public
        assert 'super-secret' not in str(public)
        unauthorized = client.post('/api/video/source/config', json={
            'admin_token': 'invalid',
        })
        assert unauthorized.status_code == 403
        authorized = client.post('/api/video/source/config', json={
            'admin_token': token,
        })
        assert authorized.status_code == 200
        assert authorized.json()['rtsp_url'] == value['rtsp_url']
        bad = client.post('/api/video/source/save', json={
            'admin_token': token, 'source': {'kind': 'rtsp', 'rtsp_url': 'https://example.com/stream'},
        })
        assert bad.status_code == 422
        bad_index = client.post('/api/video/source/save', json={
            'admin_token': token, 'source': {'kind': 'usb', 'usb_index': 30},
        })
        assert bad_index.status_code == 422
        assert client.get('/api/video/source').json()['kind'] == 'rtsp'
        assert client.post('/api/users/logout', json={'admin_token': token}).status_code == 200
        assert client.post('/api/video/source/save', json={
            'admin_token': token, 'source': {'kind': 'usb', 'usb_index': 1},
        }).status_code == 403
    with TestClient(create_app()) as reopened:
        assert reopened.get('/api/video/source').json()['kind'] == 'rtsp'
        assert reopened.app.state.video_source.current().rtsp_url == value['rtsp_url']


class FakeCamera:
    def __init__(self):
        self.frames = 0
        self.opened = True

    def isOpened(self):
        return self.opened

    def read(self):
        if not self.opened:
            return False, None
        self.frames += 1
        image = np.full((96, 96, 3), 60 + (self.frames % 70), dtype=np.uint8)
        cv2.circle(image, (48, 48), 26, (220, 220, 220), 2)
        return True, image

    def get(self, prop):
        return {
            cv2.CAP_PROP_FRAME_WIDTH: 96, cv2.CAP_PROP_FRAME_HEIGHT: 96,
            cv2.CAP_PROP_FPS: 25, cv2.CAP_PROP_FRAME_COUNT: 0,
        }.get(prop, 0)

    def set(self, prop, value):
        return True

    def release(self):
        self.opened = False


def test_live_usb_no_seek_and_camera_frame_reference_capture(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_DATA_DIR', str(tmp_path / 'data'))
    opened = []
    def fake_open(source, file_path=''):
        assert source.kind == 'usb'
        assert source.usb_index == 2
        assert not file_path
        camera = FakeCamera()
        opened.append(camera)
        return camera
    monkeypatch.setattr(video_stream, 'open_capture', fake_open)
    with TestClient(create_app()) as client:
        token = admin(client)
        saved = client.post('/api/video/source/save', json={
            'admin_token': token, 'source': {'kind': 'usb', 'usb_index': 2},
        })
        assert saved.status_code == 200
        opened_video = client.post('/api/video/open', json={
            'calibration': {'cx': 48, 'cy': 48, 'radius': 30, 'width': 96, 'height': 96},
        })
        assert opened_video.status_code == 200, opened_video.text
        data = opened_video.json()
        assert data['source_kind'] == 'usb'
        assert data['is_live'] is True
        assert data['duration_s'] == 0
        assert data['frame_count'] == 0
        assert data['frame']['result']['status'] == 'WARMUP'
        sid = data['session_id']
        assert client.post('/api/video/seek', json={
            'session_id': sid, 'time_s': 0,
        }).status_code == 422
        next_frame = client.post('/api/video/next', json={'session_id': sid})
        assert next_frame.status_code == 200, next_frame.text
        assert next_frame.json()['time_s'] > data['frame']['time_s']
        assert next_frame.json()['frame_index'] > 0
        snapshot = client.post('/api/video/snapshot', json={
            'admin_token': token,
        })
        assert snapshot.status_code == 200, snapshot.text
        assert snapshot.json()['width'] == 96
        assert snapshot.json()['height'] == 96
        assert snapshot.json()['jpeg_base64']

        assert client.post('/api/stations/calibration', json={
            'stage': 'P3', 'admin_token': token,
            'calibration': {'cx': 48, 'cy': 48, 'radius': 30, 'width': 96, 'height': 96},
        }).status_code == 200
        for _ in range(3):
            saved_ref = client.post('/api/stations/reference/live', json={
                'stage': 'P3', 'group': 'nozzle_b', 'admin_token': token,
            })
            assert saved_ref.status_code == 200, saved_ref.text
        refs = saved_ref.json()['stages']['P3']['references']
        assert len(refs) == 3
        assert all(ref['group'] == 'nozzle_b' for ref in refs)
        assert len(list((tmp_path / 'data' / 'stations').glob('*.png'))) == 3
        assert client.post('/api/stations/reference/live', json={
            'stage': 'P3', 'group': 'nozzle_b', 'admin_token': 'invalid',
        }).status_code == 403
        assert client.post('/api/video/snapshot', json={
            'admin_token': 'invalid',
        }).status_code == 403

        switched = client.post('/api/video/source/save', json={
            'admin_token': token, 'source': {'kind': 'file'},
        })
        assert switched.status_code == 200
        assert client.post('/api/video/next', json={'session_id': sid}).status_code == 409
    assert opened and all(not camera.opened for camera in opened)


def test_live_camera_disconnect_gives_error_instead_of_end_of_file(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_DATA_DIR', str(tmp_path / 'data'))
    class BrokenCamera(FakeCamera):
        def read(self):
            if self.frames > 0:
                return False, None
            return super().read()
    monkeypatch.setattr(video_stream, 'open_capture', lambda source, file_path='': BrokenCamera())
    with TestClient(create_app()) as client:
        token = admin(client)
        client.post('/api/video/source/save', json={
            'admin_token': token, 'source': {'kind': 'usb'},
        })
        opened = client.post('/api/video/open', json={
            'calibration': {'cx': 48, 'cy': 48, 'radius': 30, 'width': 96, 'height': 96},
        })
        assert opened.status_code == 200, opened.text
        packet = client.post('/api/video/next', json={
            'session_id': opened.json()['session_id'],
        })
        assert packet.status_code == 422
        assert '实时视频源' in packet.json()['detail']

def test_single_calibration_survives_restart_and_requires_admin(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_DATA_DIR', str(tmp_path / 'data'))
    coords = {'cx': 48, 'cy': 47, 'radius': 29, 'width': 96, 'height': 96}
    with TestClient(create_app()) as client:
        token = admin(client)
        denied = client.post('/api/stations/calibration/single', json={
            'calibration': coords,
        })
        assert denied.status_code == 403
        saved = client.post('/api/stations/calibration/single', json={
            'calibration': coords, 'admin_token': token,
        })
        assert saved.status_code == 200, saved.text
        assert saved.json()['single_calibration'] == coords
        profile = client.get('/api/stations/profile').json()
        assert profile['single_calibration'] == coords
    with TestClient(create_app()) as reopened:
        assert reopened.get('/api/stations/profile').json()['single_calibration'] == coords

def test_rtsp_stream_uses_saved_admin_url_and_first_frame_dimensions(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_DATA_DIR', str(tmp_path / 'data'))
    captured = []
    class CameraWithMissingMetadata(FakeCamera):
        def get(self, prop):
            if prop in (cv2.CAP_PROP_FRAME_WIDTH, cv2.CAP_PROP_FRAME_HEIGHT,
                        cv2.CAP_PROP_FPS):
                return 0
            return super().get(prop)
    def open_source(source, file_path=''):
        assert source.kind == 'rtsp'
        assert source.rtsp_url == 'rtsp://cam:secret@127.0.0.1:8554/stream'
        assert file_path == ''
        captured.append(1)
        return CameraWithMissingMetadata()
    monkeypatch.setattr(video_stream, 'open_capture', open_source)
    with TestClient(create_app()) as client:
        token = admin(client)
        response = client.post('/api/video/source/save', json={
            'admin_token': token,
            'source': {'kind': 'rtsp', 'rtsp_url': 'rtsp://cam:secret@127.0.0.1:8554/stream'},
        })
        assert response.status_code == 200
        opened = client.post('/api/video/open', json={
            'calibration': {'cx': 48, 'cy': 48, 'radius': 30, 'width': 96, 'height': 96},
        })
        assert opened.status_code == 200, opened.text
        payload = opened.json()
        assert payload['source_kind'] == 'rtsp'
        assert payload['is_live'] is True
        assert payload['width'] == 96 and payload['height'] == 96
        assert payload['fps'] == 30
        assert payload['frame']['frame_index'] == 0
        assert captured == [1]
        assert 'secret' not in str(client.get('/api/video/source').json())


def test_configured_local_file_is_persistent_and_operator_cannot_override(monkeypatch, tmp_path):
    """Operator playback must use the file selected by the administrator."""
    import base64

    monkeypatch.setenv('APP_DATA_DIR', str(tmp_path / 'data'))

    def write_video(path, count):
        writer = cv2.VideoWriter(str(path),
                                 cv2.VideoWriter_fourcc(*'MJPG'), 20, (96, 96))
        assert writer.isOpened()
        for idx in range(count):
            frame = np.full((96, 96, 3), min(255, idx * 9 + 20), np.uint8)
            writer.write(frame)
        writer.release()

    selected = tmp_path / 'saved source.avi'
    ignored = tmp_path / 'override.avi'
    write_video(selected, 50)
    write_video(ignored, 8)

    with TestClient(create_app()) as client:
        token = admin(client)
        unauthorized = client.post('/api/video/source/save', json={
            'admin_token': 'bad', 'source': {'kind': 'file', 'file_path': str(selected)},
        })
        assert unauthorized.status_code == 403
        saved = client.post('/api/video/source/save', json={
            'admin_token': token, 'source': {'kind': 'file', 'file_path': str(selected)},
        })
        assert saved.status_code == 200, saved.text
        assert saved.json()['source']['file_path'] == str(selected)
        assert 'file_path' not in client.get('/api/video/source').json()
        assert client.post('/api/video/snapshot', json={
            'admin_token': 'not-an-admin', 'time_s': 1.2,
        }).status_code == 403
        preview = client.post('/api/video/snapshot', json={
            'admin_token': token, 'time_s': 1.2,
        })
        assert preview.status_code == 200, preview.text
        info = preview.json()
        assert info['width'] == 96 and info['height'] == 96
        assert abs(info['duration_s'] - 2.5) < 0.1
        assert abs(info['time_s'] - 1.2) <= .05
        image = cv2.imdecode(np.frombuffer(base64.b64decode(info['jpeg_base64']),
                                            dtype=np.uint8), cv2.IMREAD_COLOR)
        assert image is not None and image.shape == (96, 96, 3)

        # Even a syntactically valid operator-supplied path is ignored once
        # the administrator has saved a different local source.
        opened = client.post('/api/video/open', json={
            'file_path': str(ignored),
            'calibration': {'cx': 48, 'cy': 48, 'radius': 29,
                            'width': 96, 'height': 96},
        })
        assert opened.status_code == 200, opened.text
        assert opened.json()['frame_count'] == 50
        assert opened.json()['source_kind'] == 'file'
        assert opened.json()['is_live'] is False

        bad_path = client.post('/api/video/source/save', json={
            'admin_token': token,
            'source': {'kind': 'file', 'file_path': str(tmp_path / 'missing.mp4')},
        })
        assert bad_path.status_code == 422
        assert client.post('/api/video/source/config', json={
            'admin_token': token,
        }).json()['file_path'] == str(selected)

    # A new desktop session still uses the configured video without another picker.
    with TestClient(create_app()) as reopened:
        assert reopened.app.state.video_source.current().file_path == str(selected)
        opened = reopened.post('/api/video/open', json={
            'calibration': {'cx': 48, 'cy': 48, 'radius': 29,
                            'width': 96, 'height': 96},
        })
        assert opened.status_code == 200, opened.text
        assert opened.json()['frame_count'] == 50
