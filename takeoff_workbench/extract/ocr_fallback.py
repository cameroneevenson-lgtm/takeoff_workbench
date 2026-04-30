from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import fitz


def ocr_available() -> bool:
    return hasattr(fitz.Page, "get_textpage_ocr")


def extract_ocr_text_blocks(page: Any, *, dpi: int = 200, full: bool = True) -> tuple[list[dict], Optional[str]]:
    if not ocr_available():
        return [], "PyMuPDF OCR is not available."
    try:
        text_page = page.get_textpage_ocr(dpi=dpi, full=full)
        blocks: list[dict] = []
        for item in text_page.extractBLOCKS():
            if len(item) < 5:
                continue
            x0, y0, x1, y1, text = item[:5]
            clean = " ".join(str(text or "").split())
            if not clean:
                continue
            blocks.append(
                {
                    "x0": float(x0),
                    "y0": float(y0),
                    "x1": float(x1),
                    "y1": float(y1),
                    "text": clean,
                    "block_type": "ocr",
                    "source": "ocr",
                    "confidence": 0.55,
                }
            )
        return blocks, None
    except Exception as exc:
        return [], f"OCR unavailable or failed: {exc}"


def extract_ocr_text_for_region(
    pdf_path: str | Path,
    page_number: int,
    bbox: tuple[float, float, float, float],
    *,
    dpi: int = 220,
) -> tuple[str, Optional[str]]:
    x0, y0, x1, y1 = bbox
    left, right = sorted((float(x0), float(x1)))
    top, bottom = sorted((float(y0), float(y1)))
    with fitz.open(str(pdf_path)) as doc:
        page = doc.load_page(page_number - 1)
        blocks, error = extract_ocr_text_blocks(page, dpi=dpi, full=True)
    if error and not blocks:
        return "", error
    selected: list[str] = []
    for block in blocks:
        cx = (float(block["x0"]) + float(block["x1"])) / 2.0
        cy = (float(block["y0"]) + float(block["y1"])) / 2.0
        if left <= cx <= right and top <= cy <= bottom:
            selected.append(str(block.get("text") or ""))
    return "\n".join(part for part in selected if part).strip(), error
