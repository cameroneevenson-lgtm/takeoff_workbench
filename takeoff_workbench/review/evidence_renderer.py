from __future__ import annotations

from pathlib import Path

import fitz


def crop_pdf_region(
    pdf_path: str | Path,
    page_number: int,
    bbox: tuple[float, float, float, float],
    output_path: str | Path,
    *,
    zoom: float = 2.0,
) -> str:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    x0, y0, x1, y1 = bbox
    rect = fitz.Rect(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
    with fitz.open(str(pdf_path)) as doc:
        page = doc.load_page(page_number - 1)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=rect, alpha=False)
        pix.save(str(out))
    return str(out)
