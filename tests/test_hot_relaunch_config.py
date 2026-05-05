from __future__ import annotations

from takeoff_workbench.dev.file_watcher import WATCH_EXTENSIONS, is_ignored_path
from takeoff_workbench.dev.hot_relaunch import should_restart_after_child_exit
from takeoff_workbench.dev.hot_reload_notice import format_banner_text, read_request, request_path, write_request


def test_hot_relaunch_watches_expected_extensions():
    assert {".py", ".ui", ".qss", ".json", ".csv"}.issubset(WATCH_EXTENSIONS)


def test_hot_relaunch_ignores_runtime_cache_paths():
    assert is_ignored_path(r"C:\Tools\takeoff_workbench\_runtime\app.log")
    assert is_ignored_path(r"C:\Tools\takeoff_workbench\_cache\page.png")
    assert is_ignored_path(r"C:\Tools\takeoff_workbench\.venv\Scripts\python.exe")
    assert not is_ignored_path(r"C:\Tools\takeoff_workbench\takeoff_workbench\data\material_aliases.csv")


def test_hot_reload_notice_payload_counts_down(tmp_path):
    notice_path = request_path(tmp_path / "_runtime")
    payload = write_request(
        notice_path,
        request_id="abc",
        root=tmp_path,
        changed_paths=[str(tmp_path / "app_window.py")],
        warning_seconds=10,
        now_epoch=100.0,
    )
    assert payload["deadline_epoch"] == 110.0
    loaded = read_request(notice_path, now_epoch=103.2)
    assert loaded["remaining_seconds"] == 7
    banner = format_banner_text(loaded)
    assert "Hot reload in 7s" in banner
    assert "app_window.py" in banner


def test_hot_relaunch_does_not_restart_after_manual_close_by_default():
    assert should_restart_after_child_exit(0) is False
    assert should_restart_after_child_exit(0, restart_on_clean_exit=True) is True
    assert should_restart_after_child_exit(1) is True
