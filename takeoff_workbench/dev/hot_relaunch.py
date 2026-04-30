from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from takeoff_workbench.dev.file_watcher import changed_paths, snapshot


def _runtime_dir(root: Path) -> Path:
    raw = os.environ.get("TAKEOFF_RUNTIME_DIR", "_runtime")
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _log(path: Path, message: str) -> None:
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp} {message}\n")
    print(message, flush=True)


def _spawn(root: Path, log_path: Path) -> subprocess.Popen:
    env = os.environ.copy()
    env["TAKEOFF_HOT_RELOAD_CHILD"] = "1"
    cmd = [sys.executable, str(root / "main.py")]
    _log(log_path, f"Starting child: {' '.join(cmd)}")
    return subprocess.Popen(cmd, cwd=str(root), env=env)


def _terminate(proc: subprocess.Popen, log_path: Path) -> None:
    if proc.poll() is not None:
        return
    _log(log_path, f"Stopping child pid={proc.pid}")
    try:
        proc.terminate()
    except OSError:
        return
    deadline = time.time() + 5
    while proc.poll() is None and time.time() < deadline:
        time.sleep(0.1)
    if proc.poll() is None:
        proc.kill()


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    log_path = _runtime_dir(root) / "hot_relaunch.log"
    interval = float(os.environ.get("TAKEOFF_HOT_INTERVAL", "0.7"))
    debounce = float(os.environ.get("TAKEOFF_HOT_DEBOUNCE", "1.0"))
    proc = _spawn(root, log_path)
    state = snapshot(root)
    pending_since: float | None = None
    pending_changes: list[str] = []

    def stop(signum=None, frame=None):
        _terminate(proc, log_path)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, stop)

    while True:
        time.sleep(interval)
        code = proc.poll()
        if code is not None:
            _log(log_path, f"Child exited with code {code}; watcher remains active.")
            proc = _spawn(root, log_path)
            state = snapshot(root)
            pending_since = None
            pending_changes = []
            continue
        current = snapshot(root)
        changes = changed_paths(state, current)
        if changes:
            pending_changes = changes
            pending_since = time.time()
            state = current
            _log(log_path, f"Detected {len(changes)} changed file(s).")
            continue
        if pending_since and time.time() - pending_since >= debounce:
            preview = ", ".join(Path(path).name for path in pending_changes[:5])
            _log(log_path, f"Restarting child after changes: {preview}")
            _terminate(proc, log_path)
            proc = _spawn(root, log_path)
            pending_since = None
            pending_changes = []


if __name__ == "__main__":
    raise SystemExit(main())
