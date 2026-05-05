from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Mapping


REQUEST_FILENAME = "hot_reload_request.json"


def request_path(runtime_dir: str | Path) -> Path:
    return Path(runtime_dir) / REQUEST_FILENAME


def write_request(
    path: str | Path,
    *,
    request_id: str,
    root: str | Path,
    changed_paths: list[str],
    warning_seconds: float,
    now_epoch: float | None = None,
) -> dict[str, Any]:
    now = time.time() if now_epoch is None else float(now_epoch)
    root_path = Path(root)
    rels: list[str] = []
    for changed in changed_paths:
        try:
            rels.append(str(Path(changed).resolve().relative_to(root_path.resolve())))
        except Exception:
            rels.append(str(changed))
    payload = {
        "request_id": str(request_id),
        "ts_epoch": now,
        "deadline_epoch": now + max(0.0, float(warning_seconds)),
        "warning_seconds": max(0.0, float(warning_seconds)),
        "change_count": len(changed_paths),
        "files": rels[:20],
    }
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def read_request(path: str | Path, *, now_epoch: float | None = None) -> dict[str, Any]:
    request_file = Path(path)
    if not request_file.exists():
        return {}
    try:
        payload = json.loads(request_file.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    deadline = float(payload.get("deadline_epoch", 0.0) or 0.0)
    now = time.time() if now_epoch is None else float(now_epoch)
    payload["remaining_seconds"] = max(0, int(round(deadline - now)))
    return payload


def clear_request(path: str | Path) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def format_banner_text(payload: Mapping[str, Any]) -> str:
    remaining = int(payload.get("remaining_seconds", 0) or 0)
    count = int(payload.get("change_count", 0) or 0)
    files = payload.get("files") or []
    preview = ""
    if isinstance(files, list) and files:
        preview = " Changed: " + ", ".join(str(item) for item in files[:3])
        if len(files) > 3:
            preview += ", ..."
    return f"Hot reload in {remaining}s. {count} file(s) changed.{preview}"
