"""Examples should be wired together by the application, not at import time."""

from fastapi.testclient import TestClient

from sample_backend.main import create_app


def test_separate_application_instances_have_independent_tasks():
    first = create_app()
    second = create_app()

    with TestClient(first) as a, TestClient(second) as b:
        task_id = a.post("/api/tasks/demo").json()["task_id"]
        assert a.get(f"/api/tasks/{task_id}").status_code == 200
        assert b.get(f"/api/tasks/{task_id}").status_code == 404
        a.post(f"/api/tasks/{task_id}/cancel")


def test_routes_are_registered_by_app_factory():
    """Check observable behavior instead of FastAPI's private router internals."""
    with TestClient(create_app()) as client:
        response = client.post("/api/echo", json={"message": "split modules"})
        assert response.status_code == 200
        assert response.json()["message"] == "split modules"

        assert client.get("/api/health").status_code == 200
        assert client.post("/internal/shutdown").status_code == 403

        with client.websocket_connect("/ws/events") as socket:
            assert socket.receive_json()["event"] == "system.connected"
