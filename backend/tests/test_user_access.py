"""Privilege boundaries for two device-local users, including the legacy API."""
import json

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from sample_backend.main import create_app
from sample_backend.services.water_session import DetectorSettings


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_DATA_DIR', str(tmp_path))
    with TestClient(create_app()) as c:
        yield c


def calibration():
    return {'cx': 48, 'cy': 48, 'radius': 32, 'width': 96, 'height': 96}


def test_operator_is_default_and_cannot_submit_new_settings(client):
    status = client.get('/api/users/status')
    assert status.status_code == 200
    assert status.json()['role'] == 'operator'
    assert status.json()['admin_configured'] is False
    assert status.json()['settings'] == DetectorSettings().model_dump()
    assert status.json()['settings']['station_match_threshold'] == 0.78
    payload = {'calibration': calibration(), 'sample_fps': 8}
    assert client.post('/api/detection/start', json=payload).status_code == 200
    for attempt in (
        {**payload, 'detector': {'s_water_threshold': 0.15}},
        {**payload, 'detector': DetectorSettings().model_dump()},
    ):
        denied = client.post('/api/detection/start', json=attempt)
        assert denied.status_code == 403
        assert denied.json()['detail'] == 'ADMIN_REQUIRED'
    # Video path validation happens after authorization, preventing bypass
    # even when the caller submits an otherwise valid arbitrary disk file.
    video = {'file_path': 'example.mp4', 'calibration': calibration(),
             'detector': {'s_water_threshold': 0.15}}
    assert client.post('/api/video/open', json=video).status_code == 403
    assert client.post('/api/video/open', json={
        **video, 'detector': DetectorSettings().model_dump(),
    }).status_code == 403
    assert client.post('/api/users/settings', json={
        'admin_token': 'made-up-token',
        'settings': {'s_water_threshold': 0.15},
    }).status_code == 403


def test_admin_password_switch_settings_and_logout(client, tmp_path):
    assert client.post('/api/users/setup', json={'password': 'short'}).status_code == 422
    setup = client.post('/api/users/setup', json={'password': 'Secret#9753'})
    assert setup.status_code == 200, setup.text
    token = setup.json()['admin_token']
    assert setup.json()['role'] == 'admin'
    profile = tmp_path / 'users' / 'admin.json'
    stored = profile.read_text(encoding='utf-8')
    assert 'Secret#9753' not in stored
    assert 'password_hash' in stored and 'salt' in stored
    assert client.post('/api/users/setup', json={'password': 'Other#9526'}).status_code == 409
    assert client.post('/api/users/login', json={'password': 'wrong-pass'}).status_code == 401
    settings = DetectorSettings(s_water_threshold=0.11, sector_count=12,
                                station_match_threshold=0.70)
    result = client.post('/api/users/settings', json={
        'admin_token': token, 'settings': settings.model_dump(),
    })
    assert result.status_code == 200, result.text
    assert result.json()['settings'] == settings.model_dump()

    # Operator can inspect approved settings without being able to change them.
    guest = client.get('/api/users/status').json()
    assert guest['role'] == 'operator'
    assert guest['settings']['s_water_threshold'] == .11
    assert guest['settings']['station_match_threshold'] == .70
    started = client.post('/api/detection/start', json={
        'calibration': calibration(), 'sample_fps': 8,
    })
    assert started.status_code == 200
    assert started.json()['s_water_threshold'] == 0.11
    assert started.json()['sector_count'] == 12

    # Admin may submit an explicit temporary override without saving it.
    override = client.post('/api/detection/start', json={
        'calibration': calibration(), 'sample_fps': 8,
        'detector': {'s_water_threshold': 0.2},
        'admin_token': token,
    })
    assert override.status_code == 200
    assert override.json()['s_water_threshold'] == 0.2
    assert client.get('/api/users/status').json()['settings']['s_water_threshold'] == .11

    logout = client.post('/api/users/logout', json={'admin_token': token})
    assert logout.status_code == 200
    assert client.post('/api/users/settings', json={
        'admin_token': token, 'settings': settings.model_dump(),
    }).status_code == 403
    assert client.post('/api/detection/start', json={
        'calibration': calibration(), 'detector': {}, 'admin_token': token,
    }).status_code == 403

    relog = client.post('/api/users/login', json={'password': 'Secret#9753'})
    assert relog.status_code == 200
    new_token = relog.json()['admin_token']
    assert new_token != token
    assert client.post('/api/users/logout', json={'admin_token': new_token}).status_code == 200
    assert client.post('/api/users/settings', json={
        'admin_token': new_token, 'settings': settings.model_dump(),
    }).status_code == 403
    assert json.loads(profile.read_text(encoding='utf-8'))['settings']['sector_count'] == 12


def test_operator_default_after_backend_restart_and_saved_profile_survives(client, monkeypatch, tmp_path):
    client.post('/api/users/setup', json={'password': 'Persist#123'})
    token = client.post('/api/users/login', json={'password': 'Persist#123'}).json()['admin_token']
    client.post('/api/users/settings', json={
        'admin_token': token,
        'settings': {'s_water_threshold': .23, 'sector_count': 16},
    })
    # A new backend always loses the privileged session, but not the settings.
    with TestClient(create_app()) as second:
        assert second.get('/api/users/status').json()['role'] == 'operator'
        assert second.get('/api/users/status').json()['admin_configured'] is True
        assert second.get('/api/users/status').json()['settings']['sector_count'] == 16
        assert second.post('/api/users/settings', json={
            'admin_token': token, 'settings': {},
        }).status_code == 403
        started = second.post('/api/detection/start', json={
            'calibration': calibration(),
        })
        assert started.status_code == 200
        assert started.json()['sector_count'] == 16


def test_wrong_password_rate_limited_on_local_device(client):
    client.post('/api/users/setup', json={'password': 'Another#9384'})
    for i in range(4):
        assert client.post('/api/users/login', json={
            'password': 'incorrect#12',
        }).status_code == 401
    assert client.post('/api/users/login', json={
        'password': 'incorrect#12',
    }).status_code == 429
    assert client.post('/api/users/login', json={
        'password': 'Another#9384',
    }).status_code == 429


def test_operator_video_uses_backend_approved_config(client, tmp_path):
    target = tmp_path / 'tiny.avi'
    writer = cv2.VideoWriter(str(target),
                             cv2.VideoWriter_fourcc(*'MJPG'), 30, (96, 96))
    assert writer.isOpened()
    for _ in range(5):
        writer.write(np.full((96, 96, 3), 65, dtype=np.uint8))
    writer.release()

    token = client.post('/api/users/setup', json={
        'password': 'Video#1842',
    }).json()['admin_token']
    settings = DetectorSettings(s_water_threshold=0.35, sector_count=16)
    assert client.post('/api/users/settings', json={
        'admin_token': token, 'settings': settings.model_dump(),
    }).status_code == 200
    assert client.post('/api/users/logout', json={'admin_token': token}).status_code == 200

    opened = client.post('/api/video/open', json={
        'file_path': str(target), 'calibration': calibration(),
    })
    assert opened.status_code == 200, opened.text
    assert opened.json()['s_water_threshold'] == 0.35
    assert opened.json()['sector_count'] == 16
    assert opened.json()['frame']['result']['sector_count'] == 16
    blocked = client.post('/api/video/open', json={
        'file_path': str(target), 'calibration': calibration(),
        'detector': {'sector_count': 24},
    })
    assert blocked.status_code == 403
    assert client.get('/api/users/status').json()['settings']['sector_count'] == 16
