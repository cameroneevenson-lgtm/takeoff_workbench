from __future__ import annotations

import fitz

from takeoff_workbench.data import db
from takeoff_workbench.ingest.package_ingest import ingest_pdfs
from takeoff_workbench.ingest.pdf_ingest import ingest_pdf


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
