from __future__ import annotations

from takeoff_workbench.data import db


def test_db_roundtrip_for_manual_candidate_and_review_line(tmp_path):
    db_path = tmp_path / "project.sqlite"
    db.init_db(db_path)
    with db.open_db(db_path) as conn:
        doc_id = db.upsert_document(
            conn,
            path=str(tmp_path / "drawing.pdf"),
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
        db.insert_text_blocks(
            conn,
            page_id,
            [
                {
                    "x0": 1,
                    "y0": 1,
                    "x1": 20,
                    "y1": 10,
                    "text": "1/8 ALUM PL 12 x 36",
                    "block_type": "block",
                    "source": "pymupdf",
                    "confidence": 1,
                }
            ],
        )
        region_id = db.create_region(
            conn,
            page_id=page_id,
            region_type="manual_selection",
            x0=0,
            y0=0,
            x1=30,
            y1=20,
            source="manual",
            image_crop_path=str(tmp_path / "crop.png"),
        )
        candidate_id = db.create_material_candidate(
            conn,
            {
                "page_id": page_id,
                "region_id": region_id,
                "raw_text": "1/8 ALUM PL 12 x 36",
                "raw_material_phrase": "ALUM",
                "raw_shape_phrase": "PL",
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
            },
        )
        line_id = db.create_takeoff_line_from_candidate(conn, candidate_id, reviewed_by="test")
        assert line_id > 0
    summary = db.get_project_summary(db_path)
    assert summary["documents"] == 1
    assert summary["pages"] == 1
    assert summary["candidates"] == 1
    assert summary["reviewed_lines"] == 1
