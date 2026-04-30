from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import fitz

from takeoff_workbench.data import db
from takeoff_workbench.extract.ocr_fallback import extract_ocr_text_blocks
from takeoff_workbench.extract.pdf_table_detect import likely_table_text
from takeoff_workbench.extract.pdf_text_extract import extract_text_blocks
from takeoff_workbench.extract.pdf_vector_extract import summarize_drawings


@dataclass
class PdfIngestResult:
    db_path: Path
    document_id: int
    page_count: int
    failed_pages: int = 0


def file_sha256(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def classify_page(text: str, primitive_count: int) -> str:
    upper = (text or "").upper()
    if any(term in upper for term in ("COVER", "INDEX", "REVISION HISTORY")):
        return "cover"
    if likely_table_text(upper):
        return "schedule"
    if any(term in upper for term in ("GENERAL NOTES", "NOTES")):
        return "notes"
    if any(term in upper for term in ("DETAIL", "SECTION", "TYP.")):
        return "detail"
    if primitive_count > 150:
        return "assembly"
    return "unknown"


def text_hash(blocks: list[dict]) -> str:
    joined = "\n".join(block.get("text", "") for block in blocks)
    return hashlib.sha256(joined.encode("utf-8", errors="ignore")).hexdigest()


def render_thumbnail(page: fitz.Page, output_path: Path) -> str:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    zoom = min(240.0 / max(page.rect.width, 1.0), 240.0 / max(page.rect.height, 1.0))
    zoom = max(0.08, min(zoom, 0.5))
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    pix.save(str(output_path))
    return str(output_path)


def ingest_pdf(
    pdf_path: str | Path,
    *,
    db_path: str | Path | None = None,
    cache_dir: str | Path = "_cache",
) -> PdfIngestResult:
    pdf = Path(pdf_path)
    if db_path is None:
        db_path = db.default_project_db_for_pdf(pdf)
    project_db = db.init_db(db_path)
    cache = Path(cache_dir)
    if not cache.is_absolute():
        cache = Path.cwd() / cache
    file_hash = file_sha256(pdf)

    with fitz.open(str(pdf)) as doc, db.open_db(project_db) as conn:
        page_count = doc.page_count
        document_id = db.upsert_document(
            conn,
            path=str(pdf),
            file_hash=file_hash,
            display_name=pdf.name,
            source_type="pdf",
            page_count=page_count,
        )
        db.reset_document_children(conn, document_id)
        failed_pages = 0
        for index in range(page_count):
            page_number = index + 1
            try:
                page = doc.load_page(index)
                text_blocks = extract_text_blocks(page)
                extraction_status = "extracted"
                extraction_error = None
                if not text_blocks:
                    ocr_blocks, ocr_error = extract_ocr_text_blocks(page, dpi=200, full=True)
                    if ocr_blocks:
                        text_blocks = ocr_blocks
                        extraction_status = "extracted_ocr"
                    elif ocr_error:
                        extraction_status = "extracted_ocr_unavailable"
                        extraction_error = ocr_error
                vector_summary = summarize_drawings(page)
                primitive_count = int(vector_summary.get("primitive_count") or 0)
                page_type = classify_page("\n".join(block["text"] for block in text_blocks), primitive_count)
                thumb_path = cache / "thumbnails" / f"doc_{document_id}_page_{page_number}.png"
                image_cache_path = render_thumbnail(page, thumb_path)
                page_id = db.insert_page(
                    conn,
                    document_id=document_id,
                    page_number=page_number,
                    width=float(page.rect.width),
                    height=float(page.rect.height),
                    rotation=int(page.rotation or 0),
                    page_type=page_type,
                    text_hash=text_hash(text_blocks),
                    image_cache_path=image_cache_path,
                    needs_review=page_type in {"schedule", "detail", "unknown"},
                    extraction_status=extraction_status,
                    extraction_error=extraction_error,
                )
                db.insert_text_blocks(conn, page_id, text_blocks)
                db.insert_vector_summary(conn, page_id, vector_summary)
            except Exception as exc:
                failed_pages += 1
                db.insert_page(
                    conn,
                    document_id=document_id,
                    page_number=page_number,
                    width=None,
                    height=None,
                    rotation=None,
                    page_type="unknown",
                    text_hash=None,
                    image_cache_path=None,
                    needs_review=True,
                    extraction_status="extraction_failed",
                    extraction_error=str(exc),
                )
        conn.execute(
            "UPDATE documents SET extraction_status = ?, extraction_error = ? WHERE id = ?",
            (
                "indexed_with_errors" if failed_pages else "indexed",
                f"{failed_pages} page(s) failed" if failed_pages else None,
                document_id,
            ),
        )
    return PdfIngestResult(project_db, document_id, page_count, failed_pages)
