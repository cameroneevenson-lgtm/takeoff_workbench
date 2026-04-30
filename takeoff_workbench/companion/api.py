from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, request

from takeoff_workbench.companion.auth import write_allowed
from takeoff_workbench.data import db
from takeoff_workbench.review.review_actions import accept_candidate, edit_candidate, reject_candidate


def make_api_blueprint(db_path: str | Path | None, *, readonly: bool | None = None, token: str | None = None) -> Blueprint:
    bp = Blueprint("api", __name__, url_prefix="/api")

    def require_db() -> Path | None:
        return Path(db_path) if db_path else None

    @bp.get("/project")
    def project():
        project_db = require_db()
        if project_db is None:
            return jsonify({"ok": False, "error": "TAKEOFF_COMPANION_DB is required."}), 400
        return jsonify({"ok": True, "project": db.get_project_summary(project_db)})

    @bp.get("/pages")
    def pages():
        project_db = require_db()
        if project_db is None:
            return jsonify({"ok": False, "error": "TAKEOFF_COMPANION_DB is required."}), 400
        return jsonify({"ok": True, "pages": db.list_pages(project_db)})

    @bp.get("/pages/<int:page_id>")
    def page(page_id: int):
        project_db = require_db()
        if project_db is None:
            return jsonify({"ok": False, "error": "TAKEOFF_COMPANION_DB is required."}), 400
        page_data = db.get_page(project_db, page_id)
        if not page_data:
            return jsonify({"ok": False, "error": "Page not found."}), 404
        return jsonify({"ok": True, "page": page_data})

    @bp.get("/candidates")
    def candidates():
        project_db = require_db()
        if project_db is None:
            return jsonify({"ok": False, "error": "TAKEOFF_COMPANION_DB is required."}), 400
        return jsonify({"ok": True, "candidates": db.list_candidates(project_db)})

    @bp.get("/candidates/<int:candidate_id>")
    def candidate(candidate_id: int):
        project_db = require_db()
        if project_db is None:
            return jsonify({"ok": False, "error": "TAKEOFF_COMPANION_DB is required."}), 400
        with db.open_db(project_db) as conn:
            found = db.row_to_dict(db.get_candidate(conn, candidate_id))
        if not found:
            return jsonify({"ok": False, "error": "Candidate not found."}), 404
        return jsonify({"ok": True, "candidate": found})

    @bp.post("/candidates/<int:candidate_id>/accept")
    def accept(candidate_id: int):
        project_db = require_db()
        allowed, reason = write_allowed(request, readonly=readonly, token=token)
        if not allowed:
            return jsonify({"ok": False, "error": reason}), 403
        if project_db is None:
            return jsonify({"ok": False, "error": "TAKEOFF_COMPANION_DB is required."}), 400
        payload = request.get_json(silent=True) or {}
        line_id = accept_candidate(
            project_db,
            candidate_id,
            reviewed_by=str(payload.get("reviewed_by") or "companion"),
            notes=payload.get("notes"),
        )
        return jsonify({"ok": True, "line_id": line_id})

    @bp.post("/candidates/<int:candidate_id>/reject")
    def reject(candidate_id: int):
        project_db = require_db()
        allowed, reason = write_allowed(request, readonly=readonly, token=token)
        if not allowed:
            return jsonify({"ok": False, "error": reason}), 403
        if project_db is None:
            return jsonify({"ok": False, "error": "TAKEOFF_COMPANION_DB is required."}), 400
        payload = request.get_json(silent=True) or {}
        reject_candidate(project_db, candidate_id, notes=payload.get("notes"))
        return jsonify({"ok": True})

    @bp.post("/candidates/<int:candidate_id>/edit")
    def edit(candidate_id: int):
        project_db = require_db()
        allowed, reason = write_allowed(request, readonly=readonly, token=token)
        if not allowed:
            return jsonify({"ok": False, "error": reason}), 403
        if project_db is None:
            return jsonify({"ok": False, "error": "TAKEOFF_COMPANION_DB is required."}), 400
        payload = request.get_json(silent=True) or {}
        allowed_fields = {
            "normalized_family",
            "normalized_spec",
            "normalized_shape",
            "normalized_thickness",
            "normalized_width",
            "normalized_height",
            "normalized_length",
            "normalized_unit",
            "parsed_quantity",
            "parsed_unit",
        }
        fields = {key: payload[key] for key in allowed_fields if key in payload}
        edit_candidate(project_db, candidate_id, fields, notes=payload.get("notes"))
        return jsonify({"ok": True})

    return bp
