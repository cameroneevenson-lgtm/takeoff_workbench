from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RECENT_PROJECT_FILENAME = "recent_project.json"


def runtime_dir(root: str | Path | None = None) -> Path:
    raw = os.environ.get("TAKEOFF_RUNTIME_DIR", "_runtime")
    path = Path(raw)
    if path.is_absolute():
        return path
    base = Path(root) if root is not None else Path.cwd()
    return base / path


def recent_project_file(root: str | Path | None = None) -> Path:
    return runtime_dir(root) / RECENT_PROJECT_FILENAME


def write_recent_project(project_db: str | Path, *, state_file: str | Path | None = None) -> Path:
    target = Path(state_file) if state_file is not None else recent_project_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "db_path": str(Path(project_db).resolve()),
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    temp = target.with_suffix(f"{target.suffix}.tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temp.replace(target)
    return target


def read_recent_project(*, state_file: str | Path | None = None) -> Path | None:
    target = Path(state_file) if state_file is not None else recent_project_file()
    if not target.exists():
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    raw_path = str(payload.get("db_path") or "").strip()
    if not raw_path:
        return None
    project = Path(raw_path)
    return project if project.exists() else None
