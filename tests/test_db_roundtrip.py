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


def test_remove_document_removes_only_that_pdf_project_data(tmp_path):
    db_path = tmp_path / "project.sqlite"
    db.init_db(db_path)
    with db.open_db(db_path) as conn:
        doc_ids = []
        for index in range(2):
            doc_id = db.upsert_document(
                conn,
                path=str(tmp_path / f"drawing_{index}.pdf"),
                file_hash=f"hash-{index}",
                display_name=f"drawing_{index}.pdf",
                source_type="pdf",
                page_count=1,
            )
            doc_ids.append(doc_id)
            page_id = db.insert_page(
                conn,
                document_id=doc_id,
                page_number=1,
                width=100,
                height=100,
                rotation=0,
                page_type="detail",
                text_hash=f"text-{index}",
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
                    "normalized_family": "Aluminum",
                    "normalized_shape": "Plate",
                    "normalized_unit": "in",
                    "normalization_status": "auto_normalized",
                    "candidate_status": "needs_review",
                },
            )
            db.create_takeoff_line_from_candidate(conn, candidate_id, reviewed_by="test")

    removed = db.remove_document(db_path, doc_ids[0])
    assert removed["display_name"] == "drawing_0.pdf"
    summary = db.get_project_summary(db_path)
    assert summary["documents"] == 1
    assert summary["pages"] == 1
    assert summary["candidates"] == 1
    assert summary["reviewed_lines"] == 1
    assert db.remove_document(db_path, 999999) == {}


def test_remove_documents_not_in_paths_cleans_stale_selection(tmp_path):
    db_path = tmp_path / "project.sqlite"
    db.init_db(db_path)
    kept_paths = []
    with db.open_db(db_path) as conn:
        for index in range(4):
            pdf_path = tmp_path / f"drawing_{index}.pdf"
            if index < 3:
                kept_paths.append(pdf_path)
            doc_id = db.upsert_document(
                conn,
                path=str(pdf_path),
                file_hash=f"hash-{index}",
                display_name=pdf_path.name,
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
                text_hash=f"text-{index}",
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
                    "normalized_family": "Aluminum",
                    "normalized_shape": "Plate",
                    "normalized_unit": "in",
                    "normalization_status": "auto_normalized",
                    "candidate_status": "needs_review",
                },
            )
            db.create_takeoff_line_from_candidate(conn, candidate_id, reviewed_by="test")

    removed = db.remove_documents_not_in_paths(db_path, kept_paths)
    assert [row["display_name"] for row in removed] == ["drawing_3.pdf"]
    summary = db.get_project_summary(db_path)
    assert summary["documents"] == 3
    assert summary["pages"] == 3
    assert summary["candidates"] == 3
    assert summary["reviewed_lines"] == 3


def test_project_backup_creates_resumable_project_file(tmp_path):
    db_path = tmp_path / "original.takeoff.sqlite"
    db.init_db(db_path)
    with db.open_db(db_path) as conn:
        db.upsert_document(
            conn,
            path=str(tmp_path / "drawing.pdf"),
            file_hash="abc",
            display_name="drawing.pdf",
            source_type="pdf",
            page_count=3,
        )

    saved_path = db.backup_project_db(db_path, tmp_path / "saved_project")
    assert saved_path.name == "saved_project.takeoff.sqlite"
    assert saved_path.exists()
    summary = db.get_project_summary(saved_path)
    assert summary["documents"] == 1


def test_clear_candidates_for_page_removes_regions_and_review_lines(tmp_path):
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
                    "block_type": "line",
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
                "normalized_family": "Aluminum",
                "normalized_shape": "Plate",
                "normalized_unit": "in",
                "normalization_status": "auto_normalized",
                "candidate_status": "needs_review",
            },
        )
        db.create_takeoff_line_from_candidate(conn, candidate_id, reviewed_by="test")

    counts = db.clear_candidates_for_page(db_path, page_id)

    assert counts == {"candidates": 1, "takeoff_lines": 1, "regions": 1}
    summary = db.get_project_summary(db_path)
    assert summary["documents"] == 1
    assert summary["pages"] == 1
    assert summary["candidates"] == 0
    assert summary["reviewed_lines"] == 0
    assert db.get_page(db_path, page_id)["text_blocks"]
    assert db.list_regions_for_page(db_path, page_id) == []
