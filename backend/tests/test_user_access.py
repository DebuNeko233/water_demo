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


def test_only_admin_may_change_station_roi_or_reference_frames(client, tmp_path):
    """Station writes must be protected by Python, not just hidden in Vue."""
    cal = calibration()
    endpoints = [
        ('/api/stations/calibration', {
            'stage': 'P1', 'calibration': cal,
        }),
        ('/api/stations/reference', {
            'stage': 'P1', 'file_path': str(tmp_path / 'source.avi'), 'time_s': 0,
        }),
        ('/api/stations/reference/remove', {
            'stage': 'P1', 'reference_id': 'a' * 32,
        }),
    ]
    before = client.get('/api/stations/profile').json()
    for url, payload in endpoints:
        for token_data in ({}, {'admin_token': 'invalid-token'}):
            denied = client.post(url, json={**payload, **token_data})
            assert denied.status_code == 403, (url, denied.text)
            assert denied.json()['detail'] == 'ADMIN_REQUIRED'
    assert client.get('/api/stations/profile').json() == before
    assert list((tmp_path / 'stations').glob('*.png')) == []

    token = client.post('/api/users/setup', json={
        'password': 'StationAdmin#1937',
    }).json()['admin_token']
    saved = client.post('/api/stations/calibration', json={
        'stage': 'P1', 'calibration': cal, 'admin_token': token,
    })
    assert saved.status_code == 200, saved.text
    assert saved.json()['stages']['P1']['calibration'] == cal

    source = tmp_path / 'source.avi'
    writer = cv2.VideoWriter(str(source),
                             cv2.VideoWriter_fourcc(*'MJPG'), 30, (96, 96))
    assert writer.isOpened()
    for t in range(20):
        writer.write(np.full((96, 96, 3), 50 + t, dtype=np.uint8))
    writer.release()
    captured = client.post('/api/stations/reference', json={
        'stage': 'P1', 'file_path': str(source),
        'time_s': 0, 'admin_token': token,
    })
    assert captured.status_code == 200, captured.text
    refs = captured.json()['stages']['P1']['references']
    assert len(refs) == 1
    ref_id = refs[0]['id']
    assert (tmp_path / 'stations' / (ref_id + '.png')).is_file()

    assert client.post('/api/users/logout', json={
        'admin_token': token,
    }).status_code == 200
    denied = client.post('/api/stations/reference/remove', json={
        'stage': 'P1', 'reference_id': ref_id,
        'admin_token': token,
    })
    assert denied.status_code == 403
    assert (tmp_path / 'stations' / (ref_id + '.png')).is_file()

    # No valid token survives a backend restart.
    with TestClient(create_app()) as restarted:
        assert restarted.post('/api/stations/calibration', json={
            'stage': 'P1', 'calibration': cal,
            'admin_token': token,
        }).status_code == 403
        login = restarted.post('/api/users/login', json={
            'password': 'StationAdmin#1937',
        })
        assert login.status_code == 200, login.text
        new_token = login.json()['admin_token']
        removed = restarted.post('/api/stations/reference/remove', json={
            'stage': 'P1', 'reference_id': ref_id,
            'admin_token': new_token,
        })
        assert removed.status_code == 200, removed.text
        assert removed.json()['stages']['P1']['references'] == []
