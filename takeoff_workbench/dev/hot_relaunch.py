from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from takeoff_workbench.dev.file_watcher import changed_paths, snapshot
from takeoff_workbench.dev.hot_reload_notice import clear_request, request_path, write_request


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


def should_restart_after_child_exit(code: int, *, restart_on_clean_exit: bool = False) -> bool:
    if code == 0 and not restart_on_clean_exit:
        return False
    return True


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    runtime_dir = _runtime_dir(root)
    log_path = runtime_dir / "hot_relaunch.log"
    notice_path = request_path(runtime_dir)
    interval = float(os.environ.get("TAKEOFF_HOT_INTERVAL", "0.7"))
    debounce = float(os.environ.get("TAKEOFF_HOT_DEBOUNCE", "1.0"))
    warning_seconds = float(os.environ.get("TAKEOFF_HOT_WARNING_SECONDS", "10.0"))
    restart_on_clean_exit = os.environ.get("TAKEOFF_HOT_RESTART_ON_CLOSE", "0") == "1"
    clear_request(notice_path)
    proc = _spawn(root, log_path)
    state = snapshot(root)
    pending_since: float | None = None
    pending_changes: list[str] = []
    warning_started: float | None = None
    warning_request_id = ""

    def stop(signum=None, frame=None):
        clear_request(notice_path)
        _terminate(proc, log_path)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, stop)

    while True:
        time.sleep(interval)
        code = proc.poll()
        if code is not None:
            if not should_restart_after_child_exit(code, restart_on_clean_exit=restart_on_clean_exit):
                clear_request(notice_path)
                _log(log_path, f"Child exited cleanly with code {code}; stopping hot relaunch watcher.")
                return 0
            _log(log_path, f"Child exited with code {code}; restarting child and keeping watcher active.")
            proc = _spawn(root, log_path)
            state = snapshot(root)
            pending_since = None
            pending_changes = []
            warning_started = None
            warning_request_id = ""
            clear_request(notice_path)
            continue
        current = snapshot(root)
        changes = changed_paths(state, current)
        if changes:
            pending_changes = sorted(set([*pending_changes, *changes]))
            pending_since = time.time()
            state = current
            _log(log_path, f"Detected {len(changes)} changed file(s).")
            continue
        now = time.time()
        if pending_since and warning_started is None and now - pending_since >= debounce:
            warning_started = now
            warning_request_id = str(int(now * 1000))
            preview = ", ".join(Path(path).name for path in pending_changes[:5])
            write_request(
                notice_path,
                request_id=warning_request_id,
                root=root,
                changed_paths=pending_changes,
                warning_seconds=warning_seconds,
                now_epoch=now,
            )
            _log(log_path, f"Hot reload warning shown for {warning_seconds:g}s: {preview}")
            continue
        if warning_started is not None and now - warning_started >= warning_seconds:
            preview = ", ".join(Path(path).name for path in pending_changes[:5])
            _log(log_path, f"Restarting child after changes: {preview}")
            clear_request(notice_path)
            _terminate(proc, log_path)
            proc = _spawn(root, log_path)
            pending_since = None
            pending_changes = []
            warning_started = None
            warning_request_id = ""


if __name__ == "__main__":
    raise SystemExit(main())
