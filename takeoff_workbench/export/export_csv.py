from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from takeoff_workbench.data import db
from takeoff_workbench.formatting import format_quantity


EXPORT_COLUMNS = [
    "line_id",
    "status",
    "source_pdf",
    "page_number",
    "region_id",
    "source_text",
    "raw_material_phrase",
    "raw_shape_phrase",
    "raw_dimension_phrase",
    "normalized_family",
    "normalized_spec",
    "normalized_shape",
    "thickness",
    "width",
    "height",
    "length",
    "area",
    "quantity",
    "unit",
    "weight_estimate",
    "confidence",
    "reviewed_by",
    "reviewed_at",
    "notes",
    "evidence_crop_path",
]


def reviewed_lines_dataframe(db_path: str | Path, statuses: Iterable[str] = ("reviewed", "exported")) -> pd.DataFrame:
    db.init_db(db_path)
    status_list = list(statuses)
    placeholders = ",".join("?" for _ in status_list)
    with db.open_db(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT
                tl.id AS line_id,
                tl.status,
                d.path AS source_pdf,
                p.page_number,
                r.id AS region_id,
                c.raw_text AS source_text,
                c.raw_material_phrase,
                c.raw_shape_phrase,
                c.raw_dimension_phrase,
                c.normalized_family,
                c.normalized_spec,
                c.normalized_shape,
                COALESCE(c.normalized_thickness, c.parsed_thickness) AS thickness,
                COALESCE(c.normalized_width, c.parsed_width) AS width,
                COALESCE(c.normalized_height, c.parsed_height) AS height,
                COALESCE(c.normalized_length, c.parsed_length) AS length,
                tl.area,
                tl.quantity,
                tl.unit,
                tl.weight AS weight_estimate,
                c.confidence,
                tl.reviewed_by,
                tl.reviewed_at,
                tl.review_notes AS notes,
                r.image_crop_path AS evidence_crop_path
            FROM takeoff_lines tl
            LEFT JOIN material_candidates c ON c.id = tl.candidate_id
            LEFT JOIN documents d ON d.id = tl.source_document_id
            LEFT JOIN pages p ON p.id = tl.source_page_id
            LEFT JOIN regions r ON r.id = tl.source_region_id
            WHERE tl.status IN ({placeholders})
            ORDER BY tl.id
            """,
            status_list,
        ).fetchall()
    frame = pd.DataFrame([dict(row) for row in rows])
    for column in EXPORT_COLUMNS:
        if column not in frame.columns:
            frame[column] = None
    frame = frame[EXPORT_COLUMNS]
    frame["quantity"] = frame["quantity"].map(format_quantity)
    return frame


def export_csv(db_path: str | Path, output_path: str | Path | None = None) -> Path:
    if output_path is None:
        output_path = Path(db_path).resolve().parent / "_exports" / "takeoff_export.csv"
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    frame = reviewed_lines_dataframe(db_path)
    frame.to_csv(out, index=False)
    return out
