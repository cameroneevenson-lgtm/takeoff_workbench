from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Optional


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path: str | os.PathLike[str]) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def open_db(db_path: str | os.PathLike[str]) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: str | os.PathLike[str]) -> Path:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return path


@contextmanager
def _open_ready_db(db_path: str | os.PathLike[str]) -> Iterator[sqlite3.Connection]:
    """Ensure the schema exists, then yield an open connection (committed on exit).

    Equivalent to ``init_db(db_path)`` followed by ``with open_db(db_path) as conn:``,
    which was repeated near-identically across most of the functions in this module.
    """
    init_db(db_path)
    with open_db(db_path) as conn:
        yield conn


def default_project_db_for_pdf(pdf_path: str | os.PathLike[str]) -> Path:
    pdf = Path(pdf_path)
    return pdf.with_suffix(".takeoff.sqlite")


def ensure_project_suffix(path: str | os.PathLike[str]) -> Path:
    project_path = Path(path)
    if project_path.suffix.lower() not in {".sqlite", ".db"}:
        return project_path.with_suffix(".takeoff.sqlite")
    return project_path


def backup_project_db(source_db: str | os.PathLike[str], target_db: str | os.PathLike[str]) -> Path:
    source = Path(source_db).resolve()
    target = ensure_project_suffix(target_db).resolve()
    if source == target:
        return target
    if not source.exists():
        raise FileNotFoundError(f"Project DB not found: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    source_conn = sqlite3.connect(str(source), timeout=10.0)
    target_conn = sqlite3.connect(str(target), timeout=10.0)
    try:
        source_conn.execute("PRAGMA wal_checkpoint(FULL)")
        source_conn.backup(target_conn)
        target_conn.commit()
    finally:
        target_conn.close()
        source_conn.close()
    log_event(
        target,
        "project_saved_as",
        f"Project saved as {target}",
        {"source_db": str(source), "target_db": str(target)},
    )
    return target


def row_to_dict(row: sqlite3.Row | Mapping[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return {}
    return dict(row)


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def normalized_file_key(path: str | os.PathLike[str]) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def log_event(
    db_path: str | os.PathLike[str],
    event_type: str,
    message: str,
    context: Optional[Mapping[str, Any]] = None,
) -> None:
    with _open_ready_db(db_path) as conn:
        conn.execute(
            """
            INSERT INTO app_events(event_type, message, context_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (event_type, message, json.dumps(context or {}, sort_keys=True), utc_now()),
        )


def upsert_document(
    conn: sqlite3.Connection,
    *,
    path: str,
    file_hash: str,
    display_name: str,
    source_type: str,
    page_count: int,
    extraction_status: str = "indexed",
    extraction_error: str | None = None,
) -> int:
    existing = conn.execute("SELECT id FROM documents WHERE path = ?", (path,)).fetchone()
    now = utc_now()
    if existing:
        doc_id = int(existing["id"])
        conn.execute(
            """
            UPDATE documents
            SET file_hash = ?, display_name = ?, source_type = ?, page_count = ?,
                last_scanned_at = ?, extraction_status = ?, extraction_error = ?
            WHERE id = ?
            """,
            (
                file_hash,
                display_name,
                source_type,
                page_count,
                now,
                extraction_status,
                extraction_error,
                doc_id,
            ),
        )
        return doc_id

    cur = conn.execute(
        """
        INSERT INTO documents(
            path, file_hash, display_name, source_type, page_count, created_at,
            last_scanned_at, extraction_status, extraction_error
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            path,
            file_hash,
            display_name,
            source_type,
            page_count,
            now,
            now,
            extraction_status,
            extraction_error,
        ),
    )
    return int(cur.lastrowid)


def reset_document_children(conn: sqlite3.Connection, document_id: int) -> None:
    page_rows = conn.execute("SELECT id FROM pages WHERE document_id = ?", (document_id,)).fetchall()
    page_ids = [int(row["id"]) for row in page_rows]
    if page_ids:
        marks = ",".join("?" for _ in page_ids)
        conn.execute(f"DELETE FROM takeoff_lines WHERE source_page_id IN ({marks})", page_ids)
        conn.execute(f"DELETE FROM material_candidates WHERE page_id IN ({marks})", page_ids)
        conn.execute(f"DELETE FROM regions WHERE page_id IN ({marks})", page_ids)
        conn.execute(f"DELETE FROM vector_blocks WHERE page_id IN ({marks})", page_ids)
        conn.execute(f"DELETE FROM text_blocks WHERE page_id IN ({marks})", page_ids)
    conn.execute("DELETE FROM pages WHERE document_id = ?", (document_id,))


def delete_document(conn: sqlite3.Connection, document_id: int) -> None:
    page_rows = conn.execute("SELECT id FROM pages WHERE document_id = ?", (document_id,)).fetchall()
    page_ids = [int(row["id"]) for row in page_rows]
    if page_ids:
        marks = ",".join("?" for _ in page_ids)
        conn.execute(
            f"""
            DELETE FROM takeoff_lines
            WHERE source_document_id = ?
               OR source_page_id IN ({marks})
               OR candidate_id IN (
                    SELECT id FROM material_candidates WHERE page_id IN ({marks})
               )
            """,
            [document_id, *page_ids, *page_ids],
        )
    else:
        conn.execute("DELETE FROM takeoff_lines WHERE source_document_id = ?", (document_id,))
    conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))


def remove_document(db_path: str | os.PathLike[str], document_id: int) -> dict[str, Any]:
    with _open_ready_db(db_path) as conn:
        document = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if document is None:
            return {}
        before = dict(document)
        delete_document(conn, document_id)
        conn.execute(
            """
            INSERT INTO app_events(event_type, message, context_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                "document_removed",
                f"Removed PDF from project: {before.get('display_name') or before.get('path')}",
                json.dumps(before, sort_keys=True),
                utc_now(),
            ),
        )
        return before


def list_documents(db_path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    with _open_ready_db(db_path) as conn:
        rows = conn.execute("SELECT * FROM documents ORDER BY display_name, id").fetchall()
        return rows_to_dicts(rows)


def remove_documents_not_in_paths(
    db_path: str | os.PathLike[str],
    keep_paths: Iterable[str | os.PathLike[str]],
) -> list[dict[str, Any]]:
    keep = {normalized_file_key(path) for path in keep_paths}
    removed: list[dict[str, Any]] = []
    with _open_ready_db(db_path) as conn:
        rows = conn.execute("SELECT * FROM documents ORDER BY id").fetchall()
        for row in rows:
            document = dict(row)
            if normalized_file_key(document.get("path") or "") in keep:
                continue
            delete_document(conn, int(document["id"]))
            removed.append(document)
        if removed:
            conn.execute(
                """
                INSERT INTO app_events(event_type, message, context_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    "documents_reconciled",
                    f"Removed {len(removed)} PDF(s) not in current Open PDFs selection.",
                    json.dumps({"removed": removed}, sort_keys=True),
                    utc_now(),
                ),
            )
    return removed


def insert_page(
    conn: sqlite3.Connection,
    *,
    document_id: int,
    page_number: int,
    width: float | None,
    height: float | None,
    rotation: int | None,
    page_type: str,
    text_hash: str | None,
    image_cache_path: str | None,
    needs_review: bool,
    extraction_status: str,
    extraction_error: str | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO pages(
            document_id, page_number, width, height, rotation, page_type,
            text_hash, image_cache_path, needs_review, extraction_status, extraction_error
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            document_id,
            page_number,
            width,
            height,
            rotation,
            page_type,
            text_hash,
            image_cache_path,
            1 if needs_review else 0,
            extraction_status,
            extraction_error,
        ),
    )
    return int(cur.lastrowid)


def insert_text_blocks(conn: sqlite3.Connection, page_id: int, blocks: Iterable[Mapping[str, Any]]) -> None:
    conn.executemany(
        """
        INSERT INTO text_blocks(x0, y0, x1, y1, text, block_type, source, confidence, page_id)
        VALUES (:x0, :y0, :x1, :y1, :text, :block_type, :source, :confidence, :page_id)
        """,
        [dict(block, page_id=page_id) for block in blocks],
    )


def insert_vector_summary(conn: sqlite3.Connection, page_id: int, summary: Mapping[str, Any]) -> int:
    cur = conn.execute(
        """
        INSERT INTO vector_blocks(
            page_id, x0, y0, x1, y1, primitive_count, line_count, curve_count,
            rect_count, layer_name, color, source
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            page_id,
            summary.get("x0"),
            summary.get("y0"),
            summary.get("x1"),
            summary.get("y1"),
            summary.get("primitive_count", 0),
            summary.get("line_count", 0),
            summary.get("curve_count", 0),
            summary.get("rect_count", 0),
            summary.get("layer_name"),
            summary.get("color"),
            summary.get("source", "pymupdf"),
        ),
    )
    return int(cur.lastrowid)


def create_region(
    conn: sqlite3.Connection,
    *,
    page_id: int,
    region_type: str,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    source: str,
    confidence: float | None = None,
    image_crop_path: str | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO regions(
            page_id, region_type, x0, y0, x1, y1, source,
            confidence, image_crop_path, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (page_id, region_type, x0, y0, x1, y1, source, confidence, image_crop_path, utc_now()),
    )
    return int(cur.lastrowid)


def create_material_candidate(conn: sqlite3.Connection, candidate: Mapping[str, Any]) -> int:
    now = utc_now()
    values = {
        "page_id": candidate["page_id"],
        "region_id": candidate.get("region_id"),
        "raw_text": candidate.get("raw_text", ""),
        "raw_material_phrase": candidate.get("raw_material_phrase"),
        "raw_shape_phrase": candidate.get("raw_shape_phrase"),
        "raw_dimension_phrase": candidate.get("raw_dimension_phrase"),
        "parsed_quantity": candidate.get("parsed_quantity"),
        "parsed_unit": candidate.get("parsed_unit"),
        "parsed_thickness": candidate.get("parsed_thickness"),
        "parsed_width": candidate.get("parsed_width"),
        "parsed_height": candidate.get("parsed_height"),
        "parsed_length": candidate.get("parsed_length"),
        "normalized_family": candidate.get("normalized_family"),
        "normalized_spec": candidate.get("normalized_spec"),
        "normalized_shape": candidate.get("normalized_shape"),
        "normalized_thickness": candidate.get("normalized_thickness"),
        "normalized_width": candidate.get("normalized_width"),
        "normalized_height": candidate.get("normalized_height"),
        "normalized_length": candidate.get("normalized_length"),
        "normalized_unit": candidate.get("normalized_unit"),
        "normalization_confidence": candidate.get("normalization_confidence"),
        "normalization_status": candidate.get("normalization_status", "unresolved"),
        "normalization_rule_ids": candidate.get("normalization_rule_ids"),
        "review_required": 1 if candidate.get("review_required", True) else 0,
        "candidate_status": candidate.get("candidate_status", "needs_review"),
        "confidence": candidate.get("confidence"),
        "reviewer_notes": candidate.get("reviewer_notes"),
        "created_at": now,
        "updated_at": now,
    }
    cols = ", ".join(values.keys())
    placeholders = ", ".join(f":{key}" for key in values)
    cur = conn.execute(f"INSERT INTO material_candidates({cols}) VALUES ({placeholders})", values)
    return int(cur.lastrowid)


def get_candidate(conn: sqlite3.Connection, candidate_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT c.*, p.page_number, p.document_id, r.image_crop_path,
               d.path AS source_pdf, d.display_name AS source_document
        FROM material_candidates c
        JOIN pages p ON p.id = c.page_id
        JOIN documents d ON d.id = p.document_id
        LEFT JOIN regions r ON r.id = c.region_id
        WHERE c.id = ?
        """,
        (candidate_id,),
    ).fetchone()


def update_candidate_status(
    conn: sqlite3.Connection,
    candidate_id: int,
    *,
    candidate_status: str,
    normalization_status: str | None = None,
    notes: str | None = None,
    fields: Optional[Mapping[str, Any]] = None,
) -> None:
    assignments = ["candidate_status = ?", "updated_at = ?"]
    params: list[Any] = [candidate_status, utc_now()]
    if normalization_status:
        assignments.append("normalization_status = ?")
        params.append(normalization_status)
    if notes is not None:
        assignments.append("reviewer_notes = ?")
        params.append(notes)
    for key, value in (fields or {}).items():
        if key not in {
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
        }:
            continue
        assignments.append(f"{key} = ?")
        params.append(value)
    params.append(candidate_id)
    conn.execute(f"UPDATE material_candidates SET {', '.join(assignments)} WHERE id = ?", params)


def create_takeoff_line_from_candidate(
    conn: sqlite3.Connection,
    candidate_id: int,
    *,
    reviewed_by: str = "local",
    notes: str | None = None,
) -> int:
    candidate = get_candidate(conn, candidate_id)
    if candidate is None:
        raise ValueError(f"Candidate {candidate_id} not found")
    material_bits = [candidate["normalized_family"], candidate["normalized_spec"]]
    material = " ".join(str(part) for part in material_bits if part).strip() or (
        candidate["raw_material_phrase"] or ""
    )
    profile = candidate["normalized_shape"] or candidate["raw_shape_phrase"] or ""
    dims = format_dimensions(candidate)
    cur = conn.execute(
        """
        INSERT INTO takeoff_lines(
            candidate_id, material, profile, dimensions, quantity, unit, area, weight,
            source_document_id, source_page_id, source_region_id, status,
            review_notes, reviewed_by, reviewed_at, exported_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """,
        (
            candidate_id,
            material,
            profile,
            dims,
            candidate["parsed_quantity"] or 1,
            candidate["normalized_unit"] or candidate["parsed_unit"] or "in",
            None,
            None,
            candidate["document_id"],
            candidate["page_id"],
            candidate["region_id"],
            "reviewed",
            notes if notes is not None else candidate["reviewer_notes"],
            reviewed_by,
            utc_now(),
        ),
    )
    update_candidate_status(
        conn,
        candidate_id,
        candidate_status="accepted",
        normalization_status="human_confirmed",
        notes=notes if notes is not None else candidate["reviewer_notes"],
    )
    return int(cur.lastrowid)


def format_dimensions(row: Mapping[str, Any]) -> str:
    data = dict(row)
    thickness = data.get("normalized_thickness") or data.get("parsed_thickness")
    width = data.get("normalized_width") or data.get("parsed_width")
    height = data.get("normalized_height") or data.get("parsed_height")
    length = data.get("normalized_length") or data.get("parsed_length")
    parts: list[str] = []
    if thickness is not None:
        parts.append(f"thk {thickness:g}")
    whl = [value for value in (width, height, length) if value is not None]
    if whl:
        parts.append(" x ".join(f"{float(value):g}" for value in whl))
    return " ".join(parts)


def get_project_summary(db_path: str | os.PathLike[str]) -> dict[str, Any]:
    with _open_ready_db(db_path) as conn:
        docs = conn.execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"]
        pages = conn.execute("SELECT COUNT(*) AS n FROM pages").fetchone()["n"]
        candidates = conn.execute("SELECT COUNT(*) AS n FROM material_candidates").fetchone()["n"]
        reviewed = conn.execute(
            "SELECT COUNT(*) AS n FROM takeoff_lines WHERE status IN ('reviewed', 'exported')"
        ).fetchone()["n"]
        needs_review = conn.execute(
            """
            SELECT COUNT(*) AS n FROM material_candidates
            WHERE candidate_status IN ('needs_review', 'suggested')
            """
        ).fetchone()["n"]
        return {
            "db_path": str(Path(db_path)),
            "documents": docs,
            "pages": pages,
            "candidates": candidates,
            "reviewed_lines": reviewed,
            "needs_review": needs_review,
        }


def list_pages(db_path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    with _open_ready_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT p.*, d.display_name AS document_name, d.path AS document_path,
                   COUNT(c.id) AS candidate_count
            FROM pages p
            JOIN documents d ON d.id = p.document_id
            LEFT JOIN material_candidates c ON c.page_id = p.id
            GROUP BY p.id
            ORDER BY d.display_name, p.page_number
            """
        ).fetchall()
        return rows_to_dicts(rows)


def get_page(db_path: str | os.PathLike[str], page_id: int) -> dict[str, Any]:
    with _open_ready_db(db_path) as conn:
        page = conn.execute(
            """
            SELECT p.*, d.display_name AS document_name, d.path AS document_path
            FROM pages p
            JOIN documents d ON d.id = p.document_id
            WHERE p.id = ?
            """,
            (page_id,),
        ).fetchone()
        if page is None:
            return {}
        blocks = conn.execute(
            "SELECT * FROM text_blocks WHERE page_id = ? ORDER BY y0, x0", (page_id,)
        ).fetchall()
        out = dict(page)
        out["text_blocks"] = rows_to_dicts(blocks)
        return out


def list_regions_for_page(db_path: str | os.PathLike[str], page_id: int) -> list[dict[str, Any]]:
    with _open_ready_db(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM regions WHERE page_id = ? ORDER BY id",
            (page_id,),
        ).fetchall()
        return rows_to_dicts(rows)


def clear_candidates_for_page(db_path: str | os.PathLike[str], page_id: int) -> dict[str, int]:
    with _open_ready_db(db_path) as conn:
        page = conn.execute("SELECT id FROM pages WHERE id = ?", (page_id,)).fetchone()
        if page is None:
            return {"candidates": 0, "takeoff_lines": 0, "regions": 0}
        counts = {
            "candidates": int(
                conn.execute(
                    "SELECT COUNT(*) AS n FROM material_candidates WHERE page_id = ?",
                    (page_id,),
                ).fetchone()["n"]
            ),
            "takeoff_lines": int(
                conn.execute(
                    """
                    SELECT COUNT(*) AS n
                    FROM takeoff_lines
                    WHERE source_page_id = ?
                       OR candidate_id IN (SELECT id FROM material_candidates WHERE page_id = ?)
                    """,
                    (page_id, page_id),
                ).fetchone()["n"]
            ),
            "regions": int(
                conn.execute(
                    "SELECT COUNT(*) AS n FROM regions WHERE page_id = ?",
                    (page_id,),
                ).fetchone()["n"]
            ),
        }
        conn.execute(
            """
            DELETE FROM takeoff_lines
            WHERE source_page_id = ?
               OR candidate_id IN (SELECT id FROM material_candidates WHERE page_id = ?)
            """,
            (page_id, page_id),
        )
        conn.execute("DELETE FROM material_candidates WHERE page_id = ?", (page_id,))
        conn.execute("DELETE FROM regions WHERE page_id = ?", (page_id,))
        conn.execute(
            """
            INSERT INTO app_events(event_type, message, context_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                "page_candidates_cleared",
                f"Cleared candidates for page {page_id}",
                json.dumps({"page_id": page_id, **counts}, sort_keys=True),
                utc_now(),
            ),
        )
        return counts


def list_candidates(db_path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    with _open_ready_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT c.*, p.page_number, d.display_name AS document_name, d.path AS source_pdf,
                   r.image_crop_path
            FROM material_candidates c
            JOIN pages p ON p.id = c.page_id
            JOIN documents d ON d.id = p.document_id
            LEFT JOIN regions r ON r.id = c.region_id
            ORDER BY d.display_name, p.page_number, COALESCE(r.y0, 0), c.id
            """
        ).fetchall()
        return rows_to_dicts(rows)


def get_region(db_path: str | os.PathLike[str], region_id: int) -> dict[str, Any]:
    with _open_ready_db(db_path) as conn:
        row = conn.execute("SELECT * FROM regions WHERE id = ?", (region_id,)).fetchone()
        return row_to_dict(row)


def log_companion_action(
    conn: sqlite3.Connection,
    *,
    action: str,
    target_type: str,
    target_id: int,
    old_value: Mapping[str, Any] | None,
    new_value: Mapping[str, Any] | None,
) -> None:
    conn.execute(
        """
        INSERT INTO companion_actions(
            session_id, action, target_type, target_id, old_value_json, new_value_json, created_at
        )
        VALUES (NULL, ?, ?, ?, ?, ?, ?)
        """,
        (
            action,
            target_type,
            target_id,
            json.dumps(old_value or {}, sort_keys=True),
            json.dumps(new_value or {}, sort_keys=True),
            utc_now(),
        ),
    )
