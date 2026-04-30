from __future__ import annotations

from takeoff_workbench.dev.file_watcher import WATCH_EXTENSIONS, is_ignored_path


def test_hot_relaunch_watches_expected_extensions():
    assert {".py", ".ui", ".qss", ".json", ".csv"}.issubset(WATCH_EXTENSIONS)


def test_hot_relaunch_ignores_runtime_cache_paths():
    assert is_ignored_path(r"C:\Tools\takeoff_workbench\_runtime\app.log")
    assert is_ignored_path(r"C:\Tools\takeoff_workbench\_cache\page.png")
    assert is_ignored_path(r"C:\Tools\takeoff_workbench\.venv\Scripts\python.exe")
    assert not is_ignored_path(r"C:\Tools\takeoff_workbench\takeoff_workbench\data\material_aliases.csv")
