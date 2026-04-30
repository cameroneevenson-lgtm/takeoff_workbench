from __future__ import annotations

import pandas as pd

from takeoff_workbench.data import db
from takeoff_workbench.export.export_csv import export_csv
from takeoff_workbench.export.export_xlsx import export_xlsx


def _seed_reviewed_line(db_path):
    db.init_db(db_path)
    with db.open_db(db_path) as conn:
        doc_id = db.upsert_document(
            conn,
            path="drawing.pdf",
            file_hash="abc",
            display_name="drawing.pdf",
            source_type="pdf",
            page_count=1,
        )
        page_id = db.insert_page(
            conn,
            document_id=doc_id,
            page_number=1,
            width=100,
            height=100,
            rotation=0,
            page_type="detail",
            text_hash="hash",
            image_cache_path=None,
            needs_review=True,
            extraction_status="extracted",
        )
        region_id = db.create_region(
            conn,
            page_id=page_id,
            region_type="manual_selection",
            x0=0,
            y0=0,
            x1=10,
            y1=10,
            source="manual",
            image_crop_path="crop.png",
        )
        candidate_id = db.create_material_candidate(
            conn,
            {
                "page_id": page_id,
                "region_id": region_id,
                "raw_text": "1/8 ALUM PL 12 x 36",
                "raw_material_phrase": "ALUM",
                "raw_shape_phrase": "PL",
                "raw_dimension_phrase": "1/8 x 12 x 36",
                "parsed_quantity": 1,
                "parsed_unit": "in",
                "parsed_thickness": 0.125,
                "parsed_width": 12,
                "parsed_length": 36,
                "normalized_family": "Aluminum",
                "normalized_shape": "Plate",
                "normalized_unit": "in",
                "normalization_status": "auto_normalized",
                "candidate_status": "needs_review",
                "confidence": 0.9,
            },
        )
        db.create_takeoff_line_from_candidate(conn, candidate_id, reviewed_by="test")


def test_export_creates_csv_and_xlsx(tmp_path):
    db_path = tmp_path / "project.sqlite"
    _seed_reviewed_line(db_path)
    csv_path = export_csv(db_path, tmp_path / "takeoff.csv")
    xlsx_path = export_xlsx(db_path, tmp_path / "takeoff.xlsx")
    assert csv_path.exists()
    assert xlsx_path.exists()
    frame = pd.read_csv(csv_path)
    assert list(frame["normalized_family"]) == ["Aluminum"]
