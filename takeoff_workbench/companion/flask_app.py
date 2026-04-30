from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, jsonify, render_template, send_file

from takeoff_workbench.companion.api import make_api_blueprint
from takeoff_workbench.companion.auth import is_readonly
from takeoff_workbench.data import db


def create_app(
    db_path: str | Path | None = None,
    *,
    readonly: bool | None = None,
    token: str | None = None,
) -> Flask:
    app = Flask(__name__)
    configured_db = Path(db_path) if db_path else _env_db_path()
    app.config["TAKEOFF_DB_PATH"] = str(configured_db) if configured_db else ""
    app.config["TAKEOFF_READONLY"] = is_readonly(readonly)
    app.register_blueprint(make_api_blueprint(configured_db, readonly=readonly, token=token))

    @app.get("/health")
    def health():
        return jsonify(
            {
                "ok": True,
                "service": "takeoff_workbench_companion",
                "db_configured": bool(configured_db),
                "readonly": app.config["TAKEOFF_READONLY"],
            }
        )

    @app.get("/")
    def index():
        summary = None
        error = ""
        if configured_db:
            try:
                summary = db.get_project_summary(configured_db)
            except Exception as exc:
                error = str(exc)
        else:
            error = "TAKEOFF_COMPANION_DB is required for project data."
        return render_template("index.html", summary=summary, error=error, readonly=app.config["TAKEOFF_READONLY"])

    @app.get("/candidates")
    def candidates():
        rows = []
        error = ""
        if configured_db:
            try:
                rows = db.list_candidates(configured_db)
            except Exception as exc:
                error = str(exc)
        else:
            error = "TAKEOFF_COMPANION_DB is required for candidates."
        return render_template("candidates.html", candidates=rows, error=error, readonly=app.config["TAKEOFF_READONLY"])

    @app.get("/pages/<int:page_id>")
    def page(page_id: int):
        page_data = {}
        error = ""
        if configured_db:
            try:
                page_data = db.get_page(configured_db, page_id)
                if not page_data:
                    error = "Page not found."
            except Exception as exc:
                error = str(exc)
        else:
            error = "TAKEOFF_COMPANION_DB is required for pages."
        return render_template("page.html", page=page_data, error=error)

    @app.get("/evidence/<int:region_id>")
    def evidence(region_id: int):
        if not configured_db:
            return jsonify({"ok": False, "error": "TAKEOFF_COMPANION_DB is required."}), 400
        region = db.get_region(configured_db, region_id)
        if not region:
            return jsonify({"ok": False, "error": "Region not found."}), 404
        crop = region.get("image_crop_path")
        if not crop or not Path(crop).exists():
            return jsonify({"ok": False, "error": "Evidence crop not found."}), 404
        return send_file(crop)

    return app


def _env_db_path() -> Path | None:
    raw = os.environ.get("TAKEOFF_COMPANION_DB", "").strip()
    return Path(raw) if raw else None
