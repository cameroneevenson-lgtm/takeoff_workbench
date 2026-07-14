from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QLabel

from takeoff_workbench.dev.hot_reload_notice import format_banner_text, read_request, request_path


class HotReloadController(QObject):
    """Owns the hot-reload poll timer and keeps a banner label in sync.

    Mirrors the shape of the ``HotReloadController`` classes in sibling repos
    (e.g. ``fabrication_flow_dashboard/controllers/hot_reload_controller.py``,
    ``truck_nest_explorer/controllers/hot_reload_controller.py``): a small
    controller object the main window composes rather than owning timer and
    banner wiring itself. This app's hot-reload UI is read-only (a status
    banner, no accept/cancel controls), so the controller is correspondingly
    smaller than those siblings'.
    """

    def __init__(
        self,
        banner: QLabel,
        *,
        app_root: Path,
        runtime_dir_env: str = "TAKEOFF_RUNTIME_DIR",
        interval_ms: int = 500,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._banner = banner
        self._app_root = app_root
        self._runtime_dir_env = runtime_dir_env
        self.timer = QTimer(parent)
        self.timer.setInterval(interval_ms)
        self.timer.timeout.connect(self.poll)

    def start(self) -> None:
        self.timer.start()

    def request_file_path(self) -> Path:
        runtime = Path(os.environ.get(self._runtime_dir_env, "_runtime"))
        if not runtime.is_absolute():
            runtime = self._app_root / runtime
        return request_path(runtime)

    def poll(self) -> None:
        payload = read_request(self.request_file_path())
        if not payload:
            self._banner.setVisible(False)
            return
        self._banner.setText(format_banner_text(payload))
        self._banner.setVisible(True)
