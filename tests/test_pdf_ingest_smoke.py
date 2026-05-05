from __future__ import annotations

import fitz

from takeoff_workbench.data import db
from takeoff_workbench.ingest.package_ingest import ingest_pdfs
from takeoff_workbench.ingest.pdf_ingest import ingest_pdf
from takeoff_workbench.review.review_actions import create_manual_candidates_from_region


def test_pdf_ingest_smoke_with_generated_pdf(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    page.insert_text((36, 50), "QTY 4 - 1/8 ALUM PL 12 x 36")
    page.draw_line((20, 80), (280, 80))
    doc.save(pdf_path)
    doc.close()

    result = ingest_pdf(pdf_path, db_path=tmp_path / "sample.takeoff.sqlite", cache_dir=tmp_path / "_cache")
    assert result.page_count == 1
    assert result.failed_pages == 0
    pages = db.list_pages(result.db_path)
    assert len(pages) == 1
    page_data = db.get_page(result.db_path, pages[0]["id"])
    assert "ALUM" in "\n".join(block["text"] for block in page_data["text_blocks"])
    assert any(block["block_type"] == "line" for block in page_data["text_blocks"])
    assert page_data["image_cache_path"]


def test_multiple_pdf_ingest_uses_one_project_db(tmp_path):
    pdfs = []
    for index in range(2):
        pdf_path = tmp_path / f"sample_{index}.pdf"
        doc = fitz.open()
        page = doc.new_page(width=300, height=200)
        page.insert_text((36, 50), f"QTY {index + 1} - 1/8 ALUM PL 12 x 36")
        doc.save(pdf_path)
        doc.close()
        pdfs.append(pdf_path)

    db_path = tmp_path / "takeoff_package.takeoff.sqlite"
    results = ingest_pdfs(pdfs, db_path=db_path, cache_dir=tmp_path / "_cache")
    assert [result.page_count for result in results] == [1, 1]
    summary = db.get_project_summary(db_path)
    assert summary["documents"] == 2
    assert summary["pages"] == 2


def test_manual_table_region_creates_candidate_per_row(tmp_path):
    pdf_path = tmp_path / "table.pdf"
    doc = fitz.open()
    page = doc.new_page(width=360, height=220)
    page.insert_text((36, 40), "ITEM QTY DESCRIPTION")
    page.insert_text((36, 60), "1 4 1/8 ALUM PL 12 x 36")
    page.insert_text((36, 80), "2 2 HSS 2 x 2 x 1/4")
    page.insert_text((36, 100), "3 6 M.S. FLAT BAR 2 x 1/4")
    doc.save(pdf_path)
    doc.close()

    db_path = tmp_path / "table.takeoff.sqlite"
    result = ingest_pdf(pdf_path, db_path=db_path, cache_dir=tmp_path / "_cache")
    page_id = db.list_pages(result.db_path)[0]["id"]
    candidate_ids = create_manual_candidates_from_region(
        db_path,
        page_id=page_id,
        bbox=(20, 25, 330, 118),
        audit_dir=tmp_path / "_audit",
    )

    assert len(candidate_ids) == 3
    candidates = db.list_candidates(db_path)
    assert len(candidates) == 3
    raw_texts = {candidate["raw_text"] for candidate in candidates}
    assert "1 4 1/8 ALUM PL 12 x 36" in raw_texts
    assert "2 2 HSS 2 x 2 x 1/4" in raw_texts
    assert "3 6 M.S. FLAT BAR 2 x 1/4" in raw_texts
    assert sorted(int(candidate["parsed_quantity"]) for candidate in candidates) == [2, 4, 6]
    assert len(db.list_regions_for_page(db_path, page_id)) == 1


def test_manual_table_region_reads_quantity_column(tmp_path):
    pdf_path = tmp_path / "schedule.pdf"
    doc = fitz.open()
    page = doc.new_page(width=420, height=220)
    page.insert_text((36, 40), "ITEM")
    page.insert_text((90, 40), "QTY")
    page.insert_text((145, 40), "DESCRIPTION")
    page.insert_text((36, 60), "1")
    page.insert_text((90, 60), "4")
    page.insert_text((145, 60), "1/8 ALUM PL 12 x 36")
    page.insert_text((36, 80), "2")
    page.insert_text((90, 80), "2")
    page.insert_text((145, 80), "HSS 2 x 2 x 1/4")
    doc.save(pdf_path)
    doc.close()

    db_path = tmp_path / "schedule.takeoff.sqlite"
    result = ingest_pdf(pdf_path, db_path=db_path, cache_dir=tmp_path / "_cache")
    page_id = db.list_pages(result.db_path)[0]["id"]
    create_manual_candidates_from_region(
        db_path,
        page_id=page_id,
        bbox=(20, 25, 390, 100),
        audit_dir=tmp_path / "_audit",
    )

    candidates = db.list_candidates(db_path)
    assert [int(candidate["parsed_quantity"]) for candidate in candidates] == [4, 2]
    assert candidates[0]["parsed_thickness"] == 0.125
    assert candidates[0]["parsed_width"] == 12
    assert candidates[0]["parsed_length"] == 36


def test_manual_table_region_merges_wrapped_table_entries(tmp_path):
    pdf_path = tmp_path / "wrapped_schedule.pdf"
    doc = fitz.open()
    page = doc.new_page(width=460, height=240)
    page.insert_text((36, 40), "ITEM")
    page.insert_text((90, 40), "QTY")
    page.insert_text((145, 40), "DESCRIPTION")
    page.insert_text((36, 60), "1")
    page.insert_text((90, 60), "4")
    page.insert_text((145, 60), "1/8 ALUM PL")
    page.insert_text((145, 78), "12 x 36")
    page.insert_text((36, 100), "2")
    page.insert_text((90, 100), "2")
    page.insert_text((145, 100), "HSS 2 x 2 x 1/4")
    doc.save(pdf_path)
    doc.close()

    db_path = tmp_path / "wrapped_schedule.takeoff.sqlite"
    result = ingest_pdf(pdf_path, db_path=db_path, cache_dir=tmp_path / "_cache")
    page_id = db.list_pages(result.db_path)[0]["id"]
    create_manual_candidates_from_region(
        db_path,
        page_id=page_id,
        bbox=(20, 25, 420, 122),
        audit_dir=tmp_path / "_audit",
    )

    candidates = db.list_candidates(db_path)
    assert len(candidates) == 2
    assert [int(candidate["parsed_quantity"]) for candidate in candidates] == [4, 2]
    assert candidates[0]["raw_text"] == "1 4 1/8 ALUM PL 12 x 36"
    assert candidates[0]["parsed_thickness"] == 0.125
    assert candidates[0]["parsed_width"] == 12
    assert candidates[0]["parsed_length"] == 36


def test_manual_table_region_dedupes_overlapping_ranges(tmp_path):
    pdf_path = tmp_path / "dedupe.pdf"
    doc = fitz.open()
    page = doc.new_page(width=360, height=220)
    page.insert_text((36, 40), "ITEM QTY DESCRIPTION")
    page.insert_text((36, 60), "1 4 1/8 ALUM PL 12 x 36")
    page.insert_text((36, 80), "2 2 HSS 2 x 2 x 1/4")
    page.insert_text((36, 100), "3 6 M.S. FLAT BAR 2 x 1/4")
    doc.save(pdf_path)
    doc.close()

    db_path = tmp_path / "dedupe.takeoff.sqlite"
    result = ingest_pdf(pdf_path, db_path=db_path, cache_dir=tmp_path / "_cache")
    page_id = db.list_pages(result.db_path)[0]["id"]

    first = create_manual_candidates_from_region(
        db_path,
        page_id=page_id,
        bbox=(20, 25, 330, 84),
        audit_dir=tmp_path / "_audit",
    )
    second = create_manual_candidates_from_region(
        db_path,
        page_id=page_id,
        bbox=(20, 25, 330, 118),
        audit_dir=tmp_path / "_audit",
    )
    third = create_manual_candidates_from_region(
        db_path,
        page_id=page_id,
        bbox=(20, 25, 330, 118),
        audit_dir=tmp_path / "_audit",
    )

    assert len(first) == 2
    assert len(second) == 1
    assert third == []
    candidates = db.list_candidates(db_path)
    assert len(candidates) == 3
    assert len({candidate["raw_text"] for candidate in candidates}) == 3
    assert len(db.list_regions_for_page(db_path, page_id)) == 2
