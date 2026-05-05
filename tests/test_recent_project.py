from __future__ import annotations

from takeoff_workbench.recent_project import read_recent_project, write_recent_project


def test_recent_project_roundtrip(tmp_path):
    project = tmp_path / "job.takeoff.sqlite"
    project.write_text("", encoding="utf-8")
    state = tmp_path / "_runtime" / "recent_project.json"

    write_recent_project(project, state_file=state)

    assert read_recent_project(state_file=state) == project.resolve()


def test_recent_project_ignores_missing_project(tmp_path):
    state = tmp_path / "_runtime" / "recent_project.json"
    missing = tmp_path / "missing.takeoff.sqlite"

    write_recent_project(missing, state_file=state)

    assert read_recent_project(state_file=state) is None
