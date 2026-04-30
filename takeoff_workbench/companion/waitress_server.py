from __future__ import annotations

import os
from pathlib import Path

from waitress import serve

from takeoff_workbench.companion.flask_app import create_app


def main() -> int:
    host = os.environ.get("TAKEOFF_COMPANION_HOST", "127.0.0.1")
    port = int(os.environ.get("TAKEOFF_COMPANION_PORT", "8787"))
    db_path = os.environ.get("TAKEOFF_COMPANION_DB", "").strip() or None
    runtime_dir = Path(os.environ.get("TAKEOFF_RUNTIME_DIR", "_runtime"))
    runtime_dir.mkdir(parents=True, exist_ok=True)
    log_path = runtime_dir / "companion.log"
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"Starting companion host={host} port={port} db={db_path or '<unset>'}\n")
    app = create_app(db_path)
    serve(app, host=host, port=port, threads=4)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
