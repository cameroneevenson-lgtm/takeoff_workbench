from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Mapping

import fitz

from takeoff_workbench.data import db
from takeoff_workbench.extract.material_parser import parse_material_candidate
from takeoff_workbench.extract.ocr_fallback import extract_ocr_text_for_region
from takeoff_workbench.normalize.normalization_engine import NormalizationEngine
from takeoff_workbench.review.evidence_renderer import crop_pdf_region


@dataclass(frozen=True)
class CandidateRowText:
    raw_text: str
    parse_text: str | None = None
    quantity: int | None = None


def text_inside_region(text_blocks: list[Mapping], bbox: tuple[float, float, float, float]) -> str:
    return "\n".join(rows_inside_region(text_blocks, bbox)).strip()


def rows_inside_region(text_blocks: list[Mapping], bbox: tuple[float, float, float, float]) -> list[str]:
    x0, y0, x1, y1 = bbox
    left, right = sorted((x0, x1))
    top, bottom = sorted((y0, y1))
    selected: list[dict] = []
    for block in text_blocks:
        bx0 = float(block.get("x0") or 0)
        by0 = float(block.get("y0") or 0)
        bx1 = float(block.get("x1") or 0)
        by1 = float(block.get("y1") or 0)
        if bx1 < left or bx0 > right or by1 < top or by0 > bottom:
            continue
        text = str(block.get("text") or "").strip()
        if not text:
            continue
        selected.append(
            {
                "x0": bx0,
                "y0": by0,
                "x1": bx1,
                "y1": by1,
                "cy": (by0 + by1) / 2.0,
                "text": text,
            }
        )
    return _group_blocks_into_rows(selected)


def candidate_rows_from_text(raw_text: str) -> list[str]:
    lines = [" ".join(line.split()) for line in str(raw_text or "").splitlines()]
    lines = [line for line in lines if _looks_like_candidate_row(line)]
    return lines


def candidate_row_records_from_pdf_region(
    pdf_path: str | Path,
    page_number: int,
    bbox: tuple[float, float, float, float],
) -> list[CandidateRowText]:
    word_rows = _word_rows_inside_pdf_region(pdf_path, page_number, bbox)
    if not word_rows:
        return []
    header_index, layout = _table_header_layout(word_rows)
    records: list[CandidateRowText] = []
    for index, row in enumerate(word_rows):
        raw_text = _row_text(row)
        if header_index is not None and index <= header_index:
            continue
        quantity = _quantity_from_row_layout(row, layout) if layout else None
        parse_text = _parse_text_from_row_layout(row, layout) if layout else None
        if layout and records and _is_wrapped_table_continuation(row, layout):
            previous = records[-1]
            if previous.quantity is not None or _has_table_item_quantity_prefix(previous.raw_text):
                continuation = parse_text or raw_text
                records[-1] = CandidateRowText(
                    raw_text=_join_row_text(previous.raw_text, raw_text),
                    parse_text=_join_row_text(previous.parse_text or previous.raw_text, continuation),
                    quantity=previous.quantity,
                )
                continue
        if _has_table_item_quantity_prefix(raw_text) and _looks_like_candidate_row(raw_text):
            candidate_text = raw_text
        else:
            candidate_text = parse_text if parse_text and _looks_like_candidate_row(parse_text) else raw_text
        if not _looks_like_candidate_row(candidate_text):
            continue
        records.append(CandidateRowText(raw_text=raw_text, parse_text=candidate_text, quantity=quantity))
    return records


def _group_blocks_into_rows(blocks: list[dict]) -> list[str]:
    if not blocks:
        return []
    blocks = sorted(blocks, key=lambda item: (item["cy"], item["x0"]))
    heights = [max(1.0, item["y1"] - item["y0"]) for item in blocks]
    tolerance = max(4.0, min(14.0, sorted(heights)[len(heights) // 2] * 0.75))
    grouped: list[list[dict]] = []
    for block in blocks:
        if not grouped or abs(block["cy"] - _row_center(grouped[-1])) > tolerance:
            grouped.append([block])
        else:
            grouped[-1].append(block)
    rows: list[str] = []
    for group in grouped:
        parts = []
        for block in sorted(group, key=lambda item: item["x0"]):
            text = str(block["text"])
            parts.extend(line.strip() for line in text.splitlines() if line.strip())
        row_text = " ".join(" ".join(parts).split())
        if row_text:
            rows.append(row_text)
    if len(rows) == 1:
        return candidate_rows_from_text(rows[0]) or rows
    return [row for row in rows if _looks_like_candidate_row(row)]


def _word_rows_inside_pdf_region(
    pdf_path: str | Path,
    page_number: int,
    bbox: tuple[float, float, float, float],
) -> list[list[dict]]:
    x0, y0, x1, y1 = bbox
    left, right = sorted((x0, x1))
    top, bottom = sorted((y0, y1))
    words: list[dict] = []
    with fitz.open(str(pdf_path)) as document:
        page = document.load_page(page_number - 1)
        for item in page.get_text("words"):
            if len(item) < 5:
                continue
            wx0, wy0, wx1, wy1, text = item[:5]
            if wx1 < left or wx0 > right or wy1 < top or wy0 > bottom:
                continue
            clean = " ".join(str(text or "").split())
            if not clean:
                continue
            words.append(
                {
                    "x0": float(wx0),
                    "y0": float(wy0),
                    "x1": float(wx1),
                    "y1": float(wy1),
                    "cx": (float(wx0) + float(wx1)) / 2.0,
                    "cy": (float(wy0) + float(wy1)) / 2.0,
                    "text": clean,
                }
            )
    if not words:
        return []
    words = sorted(words, key=lambda item: (item["cy"], item["x0"]))
    heights = [max(1.0, item["y1"] - item["y0"]) for item in words]
    tolerance = max(3.0, min(12.0, sorted(heights)[len(heights) // 2] * 0.7))
    rows: list[list[dict]] = []
    for word in words:
        if not rows or abs(word["cy"] - _row_center(rows[-1])) > tolerance:
            rows.append([word])
        else:
            rows[-1].append(word)
    return [sorted(row, key=lambda item: item["x0"]) for row in rows]


def _row_text(row: list[dict]) -> str:
    return " ".join(str(word["text"]) for word in sorted(row, key=lambda item: item["x0"]))


def _table_header_layout(rows: list[list[dict]]) -> tuple[int | None, list[dict]]:
    for index, row in enumerate(rows[:8]):
        headers = []
        for word in row:
            header = _normalize_header_word(str(word["text"]))
            if header:
                headers.append({"name": header, "cx": float(word["cx"])})
        names = {header["name"] for header in headers}
        if "qty" in names and names.intersection({"description", "material", "size", "part", "item"}):
            return index, sorted(headers, key=lambda item: item["cx"])
    return None, []


def _normalize_header_word(text: str) -> str | None:
    key = re.sub(r"[^A-Z0-9#]", "", text.upper())
    if key in {"QTY", "QUANTITY", "QTYREQD", "REQD"}:
        return "qty"
    if key in {"ITEM", "ITEMNO", "LINE", "LINENO", "NO", "#"}:
        return "item"
    if key in {"DESC", "DESCRIPTION"}:
        return "description"
    if key in {"MAT", "MATL", "MATERIAL"}:
        return "material"
    if key in {"SIZE", "DIM", "DIMS", "DIMENSIONS"}:
        return "size"
    if key in {"PART", "PARTNO", "PROFILE", "SHAPE"}:
        return "part"
    return None


def _has_table_item_quantity_prefix(text: str) -> bool:
    return bool(re.match(r"^\s*(?:ITEM\s*)?[A-Za-z]?\d+\s+\d+\s+", text, re.I))


def _layout_column_name(word: Mapping, layout: list[dict]) -> str | None:
    if not layout:
        return None
    cx = float(word.get("cx") or 0)
    sorted_layout = sorted(layout, key=lambda item: item["cx"])
    for index, header in enumerate(sorted_layout):
        left = float("-inf") if index == 0 else (sorted_layout[index - 1]["cx"] + header["cx"]) / 2.0
        right = (
            float("inf")
            if index == len(sorted_layout) - 1
            else (header["cx"] + sorted_layout[index + 1]["cx"]) / 2.0
        )
        if left <= cx < right:
            return str(header["name"])
    return str(sorted_layout[-1]["name"])


def _quantity_from_row_layout(row: list[dict], layout: list[dict]) -> int | None:
    for word in row:
        if _layout_column_name(word, layout) != "qty":
            continue
        text = str(word["text"]).strip()
        if re.fullmatch(r"\d+", text):
            return int(text)
    return None


def _is_wrapped_table_continuation(row: list[dict], layout: list[dict]) -> bool:
    if _quantity_from_row_layout(row, layout) is not None:
        return False
    anchor_text = _column_text(row, layout, {"item", "qty"})
    if anchor_text:
        return False
    continuation_text = _parse_text_from_row_layout(row, layout)
    return bool(continuation_text)


def _column_text(row: list[dict], layout: list[dict], columns: set[str]) -> str:
    parts = [
        str(word["text"])
        for word in row
        if _layout_column_name(word, layout) in columns
    ]
    return " ".join(parts).strip()


def _parse_text_from_row_layout(row: list[dict], layout: list[dict]) -> str | None:
    keep: list[str] = []
    for word in row:
        column = _layout_column_name(word, layout)
        if column in {"item", "qty"}:
            continue
        keep.append(str(word["text"]))
    text = " ".join(keep).strip()
    return text or None


def _join_row_text(first: str | None, second: str | None) -> str:
    return " ".join(part for part in (str(first or "").strip(), str(second or "").strip()) if part)


def _row_center(row: list[dict]) -> float:
    return sum(float(item["cy"]) for item in row) / max(1, len(row))


def _looks_like_candidate_row(text: str) -> bool:
    parsed = parse_material_candidate(text)
    has_material_or_shape = bool(parsed.raw_material_phrase or parsed.raw_shape_phrase)
    has_dimensions = bool(parsed.raw_dimension_phrase)
    return parsed.confidence >= 0.35 and (has_material_or_shape or has_dimensions)


def create_manual_candidate_from_region(
    db_path: str | Path,
    *,
    page_id: int,
    bbox: tuple[float, float, float, float],
    audit_dir: str | Path = "_audit",
    client_name: str | None = None,
) -> int:
    candidate_ids = create_manual_candidates_from_region(
        db_path,
        page_id=page_id,
        bbox=bbox,
        audit_dir=audit_dir,
        client_name=client_name,
    )
    if not candidate_ids:
        raise ValueError("No candidate rows could be created from the selected region")
    return candidate_ids[0]


def create_manual_candidates_from_region(
    db_path: str | Path,
    *,
    page_id: int,
    bbox: tuple[float, float, float, float],
    audit_dir: str | Path = "_audit",
    client_name: str | None = None,
) -> list[int]:
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
        block_dicts = [dict(row) for row in blocks]
        row_records = candidate_row_records_from_pdf_region(page["document_path"], int(page["page_number"]), bbox)
        if not row_records:
            row_records = [
                CandidateRowText(raw_text=row_text)
                for row_text in rows_inside_region(block_dicts, bbox)
            ]
        raw_text = "\n".join(record.raw_text for record in row_records).strip()
        ocr_note = None
        if not raw_text:
            raw_text, ocr_note = extract_ocr_text_for_region(
                page["document_path"],
                int(page["page_number"]),
                bbox,
                dpi=220,
            )
            row_records = [CandidateRowText(raw_text=row_text) for row_text in candidate_rows_from_text(raw_text)]
        if not row_records and raw_text:
            row_records = [CandidateRowText(raw_text=row_text) for row_text in (candidate_rows_from_text(raw_text) or [raw_text])]
        row_records = _dedupe_candidate_row_records(conn, page_id, bbox, row_records)
        if not row_records:
            return []
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
        engine = NormalizationEngine(db_path=db_path, client_name=client_name)
        candidate_ids: list[int] = []
        for row_record in row_records:
            parsed = parse_material_candidate(row_record.parse_text or row_record.raw_text).to_dict()
            parsed["raw_text"] = row_record.raw_text
            if row_record.quantity is not None:
                parsed["parsed_quantity"] = row_record.quantity
            normalized = engine.normalize(
                row_record.raw_text,
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
            candidate_ids.append(db.create_material_candidate(conn, candidate))
        return candidate_ids


def _dedupe_candidate_row_records(
    conn,
    page_id: int,
    bbox: tuple[float, float, float, float],
    records: list[CandidateRowText],
) -> list[CandidateRowText]:
    existing_keys = _existing_candidate_keys_for_overlapping_regions(conn, page_id, bbox)
    new_keys: set[str] = set()
    deduped: list[CandidateRowText] = []
    for record in records:
        key = _candidate_dedupe_key(record.raw_text)
        if not key or key in existing_keys or key in new_keys:
            continue
        new_keys.add(key)
        deduped.append(record)
    return deduped


def _existing_candidate_keys_for_overlapping_regions(
    conn,
    page_id: int,
    bbox: tuple[float, float, float, float],
) -> set[str]:
    rows = conn.execute(
        """
        SELECT c.raw_text, r.x0, r.y0, r.x1, r.y1
        FROM material_candidates c
        LEFT JOIN regions r ON r.id = c.region_id
        WHERE c.page_id = ?
        """,
        (page_id,),
    ).fetchall()
    keys: set[str] = set()
    for row in rows:
        region = (row["x0"], row["y0"], row["x1"], row["y1"])
        if None not in region and not _rectangles_overlap(bbox, region):
            continue
        key = _candidate_dedupe_key(row["raw_text"])
        if key:
            keys.add(key)
    return keys


def _candidate_dedupe_key(text: str | None) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().upper()


def _rectangles_overlap(
    first: tuple[float, float, float, float],
    second: tuple[float | None, float | None, float | None, float | None],
) -> bool:
    ax0, ay0, ax1, ay1 = (float(value) for value in first)
    bx0, by0, bx1, by1 = (float(value) for value in second if value is not None)
    a_left, a_right = sorted((ax0, ax1))
    a_top, a_bottom = sorted((ay0, ay1))
    b_left, b_right = sorted((bx0, bx1))
    b_top, b_bottom = sorted((by0, by1))
    return min(a_right, b_right) > max(a_left, b_left) and min(a_bottom, b_bottom) > max(a_top, b_top)


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
