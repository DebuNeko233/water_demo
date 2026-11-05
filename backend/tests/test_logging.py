"""Logging is useful only if it survives packaging and avoids user payloads."""

from fastapi.testclient import TestClient
from loguru import logger

from sample_backend.main import create_app


def test_backend_log_writes_events_without_echo_payload(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))
    private_text = "PRIVATE_ECHO_PAYLOAD_NEVER_LOG_ME"

    with TestClient(create_app()) as client:
        response = client.post("/api/echo", json={"message": private_text})
        assert response.status_code == 200
        assert response.json()["message"] == private_text

    # Loguru file logging uses enqueue=True; flush its queued records first.
    logger.complete()
    log_file = tmp_path / "logs" / "backend.log"
    assert log_file.is_file()
    data = log_file.read_text(encoding="utf-8")
    assert "Echo request received" in data
    assert private_text not in data
