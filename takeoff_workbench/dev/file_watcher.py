from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


WATCH_EXTENSIONS = {".py", ".ui", ".qss", ".json", ".csv"}
IGNORE_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "_runtime",
    "_cache",
    "_exports",
    "_audit",
    "logs",
    "_ml_runs",
    "_ml_models",
}


def is_ignored_path(path: str | Path) -> bool:
    parts = {part.lower() for part in Path(path).parts}
    return any(name.lower() in parts for name in IGNORE_DIR_NAMES)


def iter_watch_files(root: str | Path) -> Iterable[Path]:
    root_path = Path(root)
    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [name for name in dirnames if name.lower() not in {d.lower() for d in IGNORE_DIR_NAMES}]
        for filename in filenames:
            path = Path(dirpath) / filename
            if path.suffix.lower() in WATCH_EXTENSIONS and not is_ignored_path(path):
                yield path


def snapshot(root: str | Path) -> dict[str, tuple[int, int]]:
    state: dict[str, tuple[int, int]] = {}
    for path in iter_watch_files(root):
        try:
            stat = path.stat()
        except OSError:
            continue
        state[str(path)] = (int(stat.st_mtime_ns), int(stat.st_size))
    return state


def changed_paths(previous: dict[str, tuple[int, int]], current: dict[str, tuple[int, int]]) -> list[str]:
    changed: list[str] = []
    previous_keys = set(previous)
    current_keys = set(current)
    changed.extend(sorted(previous_keys ^ current_keys))
    for path in sorted(previous_keys & current_keys):
        if previous[path] != current[path]:
            changed.append(path)
    return changed
