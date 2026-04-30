from __future__ import annotations

from pathlib import Path

from takeoff_workbench.ingest.file_index import find_pdfs
from takeoff_workbench.ingest.pdf_ingest import PdfIngestResult, ingest_pdf


def ingest_pdfs(
    pdf_paths: list[str | Path],
    *,
    db_path: str | Path,
    cache_dir: str | Path = "_cache",
) -> list[PdfIngestResult]:
    results: list[PdfIngestResult] = []
    for pdf in pdf_paths:
        results.append(ingest_pdf(pdf, db_path=db_path, cache_dir=cache_dir))
    return results


def ingest_package(path: str | Path, *, db_path: str | Path | None = None) -> list[PdfIngestResult]:
    pdfs = find_pdfs(path)
    results: list[PdfIngestResult] = []
    for pdf in pdfs:
        results.append(ingest_pdf(pdf, db_path=db_path))
    return results
