from __future__ import annotations

from typing import Any


def extract_text_blocks(page: Any) -> list[dict]:
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
