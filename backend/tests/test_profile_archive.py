"""Round-trip, permission and rollback coverage for ZIP device configurations."""
import json
import zipfile

import cv2
import numpy as np
from fastapi.testclient import TestClient

from sample_backend.main import create_app
from sample_backend.services.water_session import DetectorSettings


def configured_client(client, tmp_path):
    source = tmp_path / "reference.avi"
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"MJPG"), 30, (96, 96))
    assert writer.isOpened()
    for i in range(80):
        image = np.full((96, 96, 3), (i * 3) % 128, np.uint8)
        cv2.circle(image, (48, 25 + 22 * (i // 25)), 23, (210, 200, 190), 2)
        writer.write(image)
    writer.release()
    for j, stage in enumerate(("P1", "P2", "P3")):
        response = client.post("/api/stations/calibration", json={
            "admin_token": admin_token(client),
            "stage": stage, "calibration": {
                "cx": 48, "cy": [25, 47, 69][j], "radius": 26,
                "width": 96, "height": 96,
            },
        })
        assert response.status_code == 200, response.text
        for i in range(3):
            response = client.post("/api/stations/reference", json={
            "admin_token": admin_token(client),
                "stage": stage, "file_path": str(source),
                "time_s": (j * 25 + i * 5) / 30,
            })
            assert response.status_code == 200, response.text
    profile = client.get("/api/stations/profile").json()
    assert profile["ready"]
    return profile


def admin_token(client):
    existing = getattr(client, '_test_admin_token', None)
    if existing:
        return existing
    password = "Profile#72914"
    reply = client.post("/api/users/login", json={"password": password})
    if reply.status_code == 409:
        reply = client.post("/api/users/setup", json={"password": password})
    assert reply.status_code == 200, reply.text
    client._test_admin_token = reply.json()["admin_token"]
    return client._test_admin_token


def test_backup_contains_roi_png_nozzle_groups_and_approved_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "data"))
    with TestClient(create_app()) as client:
        profile = configured_client(client, tmp_path)
        token = admin_token(client)
        single = {'cx': 48, 'cy': 47, 'radius': 28, 'width': 96, 'height': 96}
        assert client.post('/api/stations/calibration/single', json={
            'admin_token': token, 'calibration': single,
        }).status_code == 200
        changed = DetectorSettings(s_water_threshold=0.23, sector_count=18,
                                   station_match_threshold=0.67)
        assert client.post("/api/users/settings", json={
            "admin_token": token, "settings": changed.model_dump(),
        }).status_code == 200
        archive = tmp_path / "equipment.zip"
        missing_token = client.post("/api/stations/archive/export", json={
            "file_path": str(archive), "admin_token": "bogus",
        })
        assert missing_token.status_code == 403
        result = client.post("/api/stations/archive/export", json={
            "file_path": str(archive), "admin_token": token,
        })
        assert result.status_code == 200, result.text
        assert result.json()["reference_count"] == 9
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            assert "stations/profile.json" in names
            assert "detector/settings.json" in names
            assert "users/admin.json" not in names
            assert all("password" not in name for name in names)
            assert len([x for x in names if x.endswith(".png")]) == 9
            exported = json.loads(bundle.read("stations/profile.json"))
            assert exported["stages"]["P3"]["references"][0]["group"] == "nozzle_a"
            assert exported["single_calibration"] == single
            assert json.loads(bundle.read("detector/settings.json"))["sector_count"] == 18
            assert json.loads(bundle.read("detector/settings.json"))["station_match_threshold"] == 0.67

        first_ref = profile["stages"]["P1"]["references"][0]
        client.post("/api/stations/reference/remove", json={
            "admin_token": admin_token(client),
            "stage": "P1", "reference_id": first_ref["id"],
        })
        assert client.get("/api/stations/profile").json()["ready"] is False
        # Import changes detector settings and station data together.
        client.post("/api/users/settings", json={
            "admin_token": token, "settings": DetectorSettings().model_dump(),
        })
        unauthorized = client.post("/api/stations/archive/import", json={
            "file_path": str(archive), "admin_token": "bogus",
        })
        assert unauthorized.status_code == 403
        restored = client.post("/api/stations/archive/import", json={
            "file_path": str(archive), "admin_token": token,
        })
        assert restored.status_code == 200, restored.text
        assert restored.json()["profile"]["ready"] is True
        assert restored.json()["profile"]["single_calibration"] == single
        assert restored.json()["reference_count"] == 9
        assert restored.json()["settings"]["sector_count"] == 18
        assert restored.json()["settings"]["station_match_threshold"] == 0.67
        assert client.get("/api/users/status").json()["settings"]["sector_count"] == 18
        snap, model = client.app.state.station_profile.build(96, 96)
        assert model.ready
    # Both reconstructed data and settings survive app restart.
    with TestClient(create_app()) as reopened:
        assert reopened.get("/api/stations/profile").json()["ready"]
        assert reopened.get("/api/users/status").json()["settings"]["sector_count"] == 18


def test_invalid_archive_does_not_overwrite_previous_profile(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "data"))
    with TestClient(create_app()) as client:
        previous = configured_client(client, tmp_path)
        token = admin_token(client)
        root = tmp_path / "data" / "stations"
        profile_bytes = (root / "profile.json").read_bytes()
        images = sorted(p.name for p in root.glob("*.png"))
        broken = tmp_path / "broken.zip"
        with zipfile.ZipFile(broken, "w") as bundle:
            bundle.writestr("stations/profile.json", json.dumps(previous))
            bundle.writestr("detector/settings.json", "{}")
            bundle.writestr("manifest.json", '{"format":"zebovision-device-profile","version":1}')
            bundle.writestr("../evil.txt", "bad")
        failed = client.post("/api/stations/archive/import", json={
            "file_path": str(broken), "admin_token": token,
        })
        assert failed.status_code == 422, failed.text
        assert (root / "profile.json").read_bytes() == profile_bytes
        assert sorted(p.name for p in root.glob("*.png")) == images
        assert client.get("/api/stations/profile").json()["ready"]
        assert client.get("/api/users/status").json()["settings"] == DetectorSettings().model_dump()

        # The entry names and PNG dimensions can be correct even when pixel
        # data is corrupted; a failed OpenCV decode must reject the whole ZIP.
        good = tmp_path / "valid.zip"
        assert client.post("/api/stations/archive/export", json={
            "file_path": str(good), "admin_token": token,
        }).status_code == 200
        bad_png = tmp_path / "bad-pixels.zip"
        with zipfile.ZipFile(good) as source, zipfile.ZipFile(bad_png, "w") as destination:
            for name in source.namelist():
                raw = source.read(name)
                if name.endswith(".png"):
                    raw = raw[:24] + b"broken-pixel-data"
                destination.writestr(name, raw)
        failed = client.post("/api/stations/archive/import", json={
            "file_path": str(bad_png), "admin_token": token,
        })
        assert failed.status_code == 422, failed.text
        assert (root / "profile.json").read_bytes() == profile_bytes
        assert sorted(p.name for p in root.glob("*.png")) == images


def test_settings_save_failure_restores_original_calibration(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "data"))
    with TestClient(create_app()) as client:
        configured_client(client, tmp_path)
        token = admin_token(client)
        archive = tmp_path / "good.zip"
        assert client.post("/api/stations/archive/export", json={
            "file_path": str(archive), "admin_token": token,
        }).status_code == 200
        root = tmp_path / "data" / "stations"
        client.post("/api/stations/calibration", json={
            "admin_token": admin_token(client),
            "stage": "P1", "calibration": {
                "cx": 48, "cy": 38, "radius": 26, "width": 96, "height": 96,
            },
        })
        previous = (root / "profile.json").read_bytes()
        images = sorted(p.name for p in root.glob("*.png"))
        def crash(_token, _settings):
            raise OSError("simulated disk failure")
        monkeypatch.setattr(client.app.state.user_access, "update_settings", crash)
        failed = client.post("/api/stations/archive/import", json={
            "file_path": str(archive), "admin_token": token,
        })
        assert failed.status_code == 422
        assert (root / "profile.json").read_bytes() == previous
        assert sorted(p.name for p in root.glob("*.png")) == images
        assert client.get("/api/stations/profile").json()["stages"]["P1"]["calibration"]["cy"] == 38
