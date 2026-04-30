from __future__ import annotations

from pathlib import Path
from typing import Mapping

from takeoff_workbench.data import db
from takeoff_workbench.extract.material_parser import parse_material_candidate
from takeoff_workbench.extract.ocr_fallback import extract_ocr_text_for_region
from takeoff_workbench.normalize.normalization_engine import NormalizationEngine
from takeoff_workbench.review.evidence_renderer import crop_pdf_region


def text_inside_region(text_blocks: list[Mapping], bbox: tuple[float, float, float, float]) -> str:
    x0, y0, x1, y1 = bbox
    left, right = sorted((x0, x1))
    top, bottom = sorted((y0, y1))
    selected: list[str] = []
    for block in text_blocks:
        bx0 = float(block.get("x0") or 0)
        by0 = float(block.get("y0") or 0)
        bx1 = float(block.get("x1") or 0)
        by1 = float(block.get("y1") or 0)
        cx = (bx0 + bx1) / 2.0
        cy = (by0 + by1) / 2.0
        if left <= cx <= right and top <= cy <= bottom:
            selected.append(str(block.get("text") or ""))
    return "\n".join(part for part in selected if part).strip()


def create_manual_candidate_from_region(
    db_path: str | Path,
    *,
    page_id: int,
    bbox: tuple[float, float, float, float],
    audit_dir: str | Path = "_audit",
    client_name: str | None = None,
) -> int:
    db.init_db(db_path)
    with db.open_db(db_path) as conn:
        page = conn.execute(
            """
            SELECT p.*, d.path AS document_path
            FROM pages p
            JOIN documents d ON d.id = p.document_id
            WHERE p.id = ?
            """,
            (page_id,),
        ).fetchone()
        if page is None:
            raise ValueError(f"Page {page_id} not found")
        blocks = conn.execute("SELECT * FROM text_blocks WHERE page_id = ?", (page_id,)).fetchall()
        raw_text = text_inside_region([dict(row) for row in blocks], bbox)
        ocr_note = None
        if not raw_text:
            raw_text, ocr_note = extract_ocr_text_for_region(
                page["document_path"],
                int(page["page_number"]),
                bbox,
                dpi=220,
            )
        crop_path = Path(audit_dir) / f"region_page_{page['page_number']}_{page_id}.png"
        if not crop_path.is_absolute():
            crop_path = Path(db_path).resolve().parent / crop_path
        crop_pdf_region(page["document_path"], int(page["page_number"]), bbox, crop_path)
        region_id = db.create_region(
            conn,
            page_id=page_id,
            region_type="manual_selection",
            x0=float(bbox[0]),
            y0=float(bbox[1]),
            x1=float(bbox[2]),
            y1=float(bbox[3]),
            source="manual",
            confidence=1.0,
            image_crop_path=str(crop_path),
        )
        parsed = parse_material_candidate(raw_text).to_dict()
        normalized = NormalizationEngine(db_path=db_path, client_name=client_name).normalize(
            raw_text,
            raw_shape_phrase=parsed.get("raw_shape_phrase"),
            parsed_unit=parsed.get("parsed_unit"),
        )
        candidate = {
            "page_id": page_id,
            "region_id": region_id,
            **parsed,
            **normalized.to_candidate_fields(),
            "normalized_thickness": parsed.get("parsed_thickness"),
            "normalized_width": parsed.get("parsed_width"),
            "normalized_height": parsed.get("parsed_height"),
            "normalized_length": parsed.get("parsed_length"),
            "review_required": True,
            "candidate_status": "needs_review",
            "confidence": parsed.get("confidence"),
            "reviewer_notes": ocr_note if ocr_note else None,
        }
        return db.create_material_candidate(conn, candidate)


def accept_candidate(db_path: str | Path, candidate_id: int, *, reviewed_by: str = "local", notes: str | None = None) -> int:
    db.init_db(db_path)
    with db.open_db(db_path) as conn:
        old = db.row_to_dict(db.get_candidate(conn, candidate_id))
        line_id = db.create_takeoff_line_from_candidate(conn, candidate_id, reviewed_by=reviewed_by, notes=notes)
        new = db.row_to_dict(db.get_candidate(conn, candidate_id))
        db.log_companion_action(
            conn,
            action="accept",
            target_type="candidate",
            target_id=candidate_id,
            old_value=old,
            new_value=new,
        )
        return line_id


def reject_candidate(db_path: str | Path, candidate_id: int, *, notes: str | None = None) -> None:
    db.init_db(db_path)
    with db.open_db(db_path) as conn:
        old = db.row_to_dict(db.get_candidate(conn, candidate_id))
        db.update_candidate_status(
            conn,
            candidate_id,
            candidate_status="rejected",
            normalization_status="rejected",
            notes=notes,
        )
        new = db.row_to_dict(db.get_candidate(conn, candidate_id))
        db.log_companion_action(
            conn,
            action="reject",
            target_type="candidate",
            target_id=candidate_id,
            old_value=old,
            new_value=new,
        )


def edit_candidate(db_path: str | Path, candidate_id: int, fields: Mapping, *, notes: str | None = None) -> None:
    db.init_db(db_path)
    with db.open_db(db_path) as conn:
        old = db.row_to_dict(db.get_candidate(conn, candidate_id))
        db.update_candidate_status(
            conn,
            candidate_id,
            candidate_status="edited",
            normalization_status="human_edited",
            notes=notes,
            fields=fields,
        )
        new = db.row_to_dict(db.get_candidate(conn, candidate_id))
        db.log_companion_action(
            conn,
            action="edit",
            target_type="candidate",
            target_id=candidate_id,
            old_value=old,
            new_value=new,
        )
