from __future__ import annotations

from takeoff_workbench.companion.flask_app import create_app
from takeoff_workbench.data import db


def test_companion_health_returns_ok():
    app = create_app()
    client = app.test_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["ok"] is True


def test_companion_project_summary_and_write_token_required(tmp_path):
    db_path = tmp_path / "project.sqlite"
    db.init_db(db_path)
    app = create_app(db_path, token="secret")
    client = app.test_client()
    project = client.get("/api/project")
    assert project.status_code == 200
    assert project.get_json()["project"]["documents"] == 0
    denied = client.post("/api/candidates/1/accept", json={})
    assert denied.status_code == 403
