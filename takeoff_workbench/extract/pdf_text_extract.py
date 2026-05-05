from __future__ import annotations

from typing import Any


def extract_text_blocks(page: Any) -> list[dict]:
    line_blocks = _extract_text_lines(page)
    if line_blocks:
        return line_blocks
    return _extract_text_blocks_fallback(page)


def _extract_text_lines(page: Any) -> list[dict]:
    blocks: list[dict] = []
    page_dict = page.get_text("dict")
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = " ".join(str(span.get("text") or "").strip() for span in spans)
            clean = " ".join(text.split())
            if not clean:
                continue
            bbox = line.get("bbox") or block.get("bbox")
            if not bbox or len(bbox) < 4:
                continue
            x0, y0, x1, y1 = bbox[:4]
            blocks.append(
                {
                    "x0": float(x0),
                    "y0": float(y0),
                    "x1": float(x1),
                    "y1": float(y1),
                    "text": clean,
                    "block_type": "line",
                    "source": "pymupdf",
                    "confidence": 1.0,
                }
            )
    return blocks


def _extract_text_blocks_fallback(page: Any) -> list[dict]:
    blocks: list[dict] = []
    for item in page.get_text("blocks"):
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
                "block_type": "block",
                "source": "pymupdf",
                "confidence": 1.0,
            }
        )
    return blocks
