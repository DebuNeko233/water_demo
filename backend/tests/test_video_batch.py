"""Every source frame still contributes to OK/NG and CSV when display is batched."""
from __future__ import annotations

import cv2
import numpy as np
from fastapi.testclient import TestClient

from sample_backend.main import create_app
from sample_backend.services.water_detection import Calibration, DemoConfig, WaterDetector
from sample_backend.services import video_stream


def make_video(tmp_path, count=11, fps=30):
    path = tmp_path / 'batch.avi'
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'),
                             fps, (96, 96))
    assert writer.isOpened()
    for i in range(count):
        rng = np.random.default_rng(i)
        pixels = rng.integers(40, 200, size=(96, 96, 3), dtype=np.uint8)
        writer.write(pixels)
    writer.release()
    return path


def open_video(client, path, time_s=0):
    return client.post('/api/video/open', json={
        'file_path': str(path), 'start_time_s': time_s,
        'calibration': {
            'cx': 48, 'cy': 48, 'radius': 32, 'width': 96, 'height': 96,
        },
    })


def test_batch_analyzes_every_frame_with_only_one_jpeg_and_exact_timeline(tmp_path, monkeypatch):
    source = make_video(tmp_path)
    original_imencode = cv2.imencode
    jpeg_calls = []

    def spy_imencode(format, img, *args):
        if format == '.jpg':
            jpeg_calls.append(img.shape[:2])
        return original_imencode(format, img, *args)

    monkeypatch.setattr(video_stream.cv2, 'imencode', spy_imencode)
    reference_video = cv2.VideoCapture(str(source))
    baseline = WaterDetector((96, 96), 30, Calibration(48, 48, 32),
                             DemoConfig())
    expected = []
    while True:
        ok, raw = reference_video.read()
        if not ok:
            break
        expected.append(baseline.process(raw))
    reference_video.release()

    with TestClient(create_app()) as client:
        first = open_video(client, source)
        assert first.status_code == 200, first.text
        first_packet = first.json()['frame']
        assert first_packet['frame_index'] == 0
        assert len(jpeg_calls) == 1

        session = first.json()['session_id']
        results = [first_packet['result']]
        last_times = []
        for _ in range(5):
            response = client.post('/api/video/next', json={
                'session_id': session, 'batch_frames': 3,
            })
            assert response.status_code == 200, response.text
            packet = response.json()
            if packet['ended']:
                break
            assert packet['performance']['frames'] >= 1
            for metric in ('decode_ms', 'analysis_ms', 'preview_ms'):
                assert packet['performance'][metric] >= 0
            batch = packet['samples'] + [packet['result']]
            assert len(batch) == packet['performance']['frames']
            assert batch[-1] == packet['result']
            assert [r['frame_index'] for r in batch] == list(
                range(results[-1]['frame_index'] + 1,
                      results[-1]['frame_index'] + 1 + len(batch)))
            assert all(isinstance(row['history'], list) for row in batch)
            results.extend(batch)
            last_times.append(packet['time_s'])
        assert len(results) == len(expected)
        assert [r['frame_index'] for r in results] == list(range(len(expected)))
        assert [round(t, 6) for t in last_times] == [round(x/30, 6) for x in (3, 6, 9, 10)]
        assert len(jpeg_calls) == 1 + len(last_times)
        for i, (actual, truth) in enumerate(zip(results, expected)):
            for key in ('status', 's_water', 'abnormal_run_s', 'history_ready',
                        'max_sector_idx', 'max_sector_score', 'sector_scores'):
                assert actual[key] == truth[key], (i, key, actual[key], truth[key])
        assert client.post('/api/video/next', json={
            'session_id': session, 'batch_frames': 3,
        }).json() == {'ended': True}


def test_batch_does_not_seek_after_pause_and_seek_restarts_detector(tmp_path):
    source = make_video(tmp_path, count=18)
    with TestClient(create_app()) as client:
        opened = open_video(client, source).json()
        sid = opened['session_id']
        batched = client.post('/api/video/next', json={
            'session_id': sid, 'batch_frames': 4,
        })
        assert batched.status_code == 200
        assert batched.json()['frame_index'] == 4
        assert [row['frame_index'] for row in batched.json()['samples']] == [1, 2, 3]

        # No read requests during pause => source cursor stays at frame 5.
        one = client.post('/api/video/next', json={
            'session_id': sid,
        }).json()
        assert one['frame_index'] == 5
        assert 'samples' not in one
        assert one['performance']['frames'] == 1

        seeked = client.post('/api/video/seek', json={
            'session_id': sid, 'time_s': 10 / 30,
        })
        assert seeked.status_code == 200, seeked.text
        assert seeked.json()['frame_index'] == 10
        assert seeked.json()['result']['status'] == 'WARMUP'
        after = client.post('/api/video/next', json={
            'session_id': sid, 'batch_frames': 3,
        })
        assert after.json()['frame_index'] == 13
        assert [s['frame_index'] for s in after.json()['samples']] == [11, 12]


def test_batch_validation_does_not_allow_unbounded_work(tmp_path):
    source = make_video(tmp_path, count=6)
    with TestClient(create_app()) as client:
        sid = open_video(client, source).json()['session_id']
        for invalid in [0, 7, -3, 100_000]:
            response = client.post('/api/video/next', json={
                'session_id': sid, 'batch_frames': invalid,
            })
            assert response.status_code == 422
        # Invalid batches must not advance the decoder.
        assert client.post('/api/video/next', json={
            'session_id': sid,
        }).json()['frame_index'] == 1
