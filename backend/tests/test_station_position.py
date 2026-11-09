"""Three-position reference-frame calibration and selection regression."""
import math
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

from sample_backend.main import create_app
from sample_backend.services.station_position import (
    STAGES, ReferencePositionRecognizer, StageProfileStore,
    StageCalibrationInput, StageReferenceInput, edge_descriptor,
)
from sample_backend.services.water_detection import Calibration, DemoConfig, WaterDetector


def wafer_frame(stage: str, t: int, size=96):
    # Fixed distinct wafer appearance, moving spray/nozzle per frame.
    rng = np.random.default_rng({'P1': 11, 'P2': 22, 'P3': 33}[stage])
    h = w = size
    image = np.full((h, w, 3), 45, dtype=np.uint8)
    centers = {'P1': (48, 26), 'P2': (48, 48), 'P3': (48, 70)}
    cx, cy = centers[stage]
    yy, xx = np.indices((h, w))
    d2 = (xx-cx)**2 + (yy-cy)**2
    image[d2 <= 24**2] = rng.integers(105, 155, size=3)
    rim = (d2 >= 23**2) & (d2 <= 25**2)
    image[rim] = (210, 220, 230)
    for k in range(12):
        ang = 2 * np.pi * k / 12
        px, py = int(cx + 18 * np.cos(ang)), int(cy + 18 * np.sin(ang))
        cv2.circle(image, (px, py), 2, (40, 40, 40), -1)
    cv2.line(image, (t * 7 % w, 0), (t * 7 % w, h - 1),
             (100, 100, 110), 1)
    return image


def make_video(tmp_path: Path):
    path = tmp_path / 'three.avi'
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 30, (96, 96))
    assert writer.isOpened()
    for s in STAGES:
        for t in range(25):
            writer.write(wafer_frame(s, t))
    writer.release()
    return path


def build_profile(client, source):
    for i, stage in enumerate(STAGES):
        cy = [26, 48, 70][i]
        resp = client.post('/api/stations/calibration', json={
            'stage': stage, 'calibration': {
                'cx': 48, 'cy': cy, 'radius': 26,
                'width': 96, 'height': 96,
            },
        })
        assert resp.status_code == 200, resp.text
        for j in range(5):
            time_s = (i * 25 + j * 5) / 30
            response = client.post('/api/stations/reference', json={
                'stage': stage, 'file_path': str(source), 'time_s': time_s,
            })
            assert response.status_code == 200, response.text
    return client.get('/api/stations/profile').json()


def test_all_three_stations_capture_persist_and_abstain(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_DATA_DIR', str(tmp_path / 'app-data'))
    source = make_video(tmp_path)
    with TestClient(create_app()) as client:
        assert client.get('/api/stations/profile').json()['ready'] is False
        profile = build_profile(client, source)
        assert profile['ready'] is True
        for stage in STAGES:
            assert len(profile['stages'][stage]['references']) == 5
        saved = list((tmp_path / 'app-data' / 'stations').glob('*.png'))
        assert len(saved) == 15
        store = client.app.state.station_profile
        snap, model = store.build(96, 96)
        assert model.ready
        for stage in STAGES:
            choice, conf, scores = model.classify(wafer_frame(stage, 1))
            assert choice == stage, (stage, choice, conf, scores)
        assert model.classify(np.zeros((96,96,3), dtype=np.uint8))[0] == 'UNKNOWN'
        sample = profile['stages']['P1']['references'][0]
        duplicate = client.post('/api/stations/reference', json={
            'stage': 'P1', 'file_path': str(source), 'time_s': sample['time_s'],
        })
        assert duplicate.status_code == 422
        deleted = client.post('/api/stations/reference/remove', json={
            'stage': 'P1', 'reference_id': sample['id'],
        })
        assert deleted.status_code == 200
        assert deleted.json()['ready'] is False
    with TestClient(create_app()) as client:
        assert len(client.get('/api/stations/profile').json()['stages']['P1']['references']) == 4


def test_auto_video_pauses_until_stable_then_matches_original_detector(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_DATA_DIR', str(tmp_path / 'profile'))
    source = make_video(tmp_path)
    with TestClient(create_app()) as client:
        blocked = client.post('/api/video/open', json={
            'file_path': str(source), 'stage_mode': 'auto',
            'calibration': {'cx':48, 'cy':26, 'radius':26, 'width':96, 'height':96},
        })
        assert blocked.status_code == 422
        build_profile(client, source)
        opened = client.post('/api/video/open', json={
            'file_path': str(source), 'stage_mode': 'auto',
            'calibration': {'cx':48, 'cy':26, 'radius':26, 'width':96, 'height':96},
        })
        assert opened.status_code == 200, opened.text
        session = opened.json()
        assert session['stage_mode'] == 'auto'
        sid = session['session_id']
        first = session['frame']
        assert first['result']['status'] == 'PAUSED'
        assert first['result']['reason'] == 'POSITION_UNSTABLE'
        assert first['result']['stage'] == 'P1'
        assert first['result']['s_water'] == 0.0
        second = client.post('/api/video/next', json={'session_id':sid}).json()
        assert second['result']['status'] == 'PAUSED'
        third = client.post('/api/video/next', json={'session_id':sid}).json()
        assert third['result']['stage'] == 'P1'
        assert third['result']['status'] == 'WARMUP'
        # Original WaterDetector first frame on the same source image.
        cap = cv2.VideoCapture(str(source))
        cap.set(cv2.CAP_PROP_POS_FRAMES, 2)
        ok, frame = cap.read()
        assert ok
        direct = WaterDetector((96,96), 30, Calibration(48,26,26), DemoConfig())
        truth = direct.process(frame)
        assert third['result']['s_water'] == truth['s_water']
        assert third['result']['history_ready'] == truth['history_ready']
        cap.release()
        # During stage transitions, values MUST NOT carry over as false OK/NG.
        states = [third['result']]
        for _ in range(34):
            states.append(client.post('/api/video/next', json={'session_id': sid}).json()['result'])
        assert any(x['stage']=='P2' and x['status']=='PAUSED' for x in states)
        assert any(x['stage']=='P2' and x['status']=='WARMUP' for x in states)
        assert all(x['status'] not in ('OK','NG') or x['history_ready'] for x in states)


def test_profiles_reject_mismatched_resolution(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_DATA_DIR', str(tmp_path / 'profile'))
    source = make_video(tmp_path)
    with TestClient(create_app()) as client:
        build_profile(client, source)
        mismatch = client.post('/api/video/open', json={
            'file_path': str(source),
            'stage_mode': 'auto',
            'calibration': {'cx':48, 'cy':26, 'radius':26, 'width':96,'height':96},
        })
        assert mismatch.status_code == 200
        client.post('/api/stations/calibration', json={
            'stage':'P3','calibration':{'cx':48,'cy':70,'radius':26,'width':120,'height':96},
        })
        assert client.get('/api/stations/profile').json()['ready'] is False
        invalid = client.post('/api/video/open', json={
            'file_path': str(source), 'stage_mode':'auto',
            'calibration': {'cx':48, 'cy':26, 'radius':26, 'width':96, 'height':96},
        })
        assert invalid.status_code == 422
