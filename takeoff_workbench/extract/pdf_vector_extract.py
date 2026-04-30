from __future__ import annotations

from math import inf
from typing import Any


def summarize_drawings(page: Any) -> dict:
    drawings = page.get_drawings()
    x0 = y0 = inf
    x1 = y1 = -inf
    line_count = 0
    curve_count = 0
    rect_count = 0
    primitive_count = 0
    for drawing in drawings:
        rect = drawing.get("rect")
        if rect:
            x0 = min(x0, float(rect.x0))
            y0 = min(y0, float(rect.y0))
            x1 = max(x1, float(rect.x1))
            y1 = max(y1, float(rect.y1))
        for item in drawing.get("items", []):
            primitive_count += 1
            op = item[0] if item else ""
            if op == "l":
                line_count += 1
            elif op == "re":
                rect_count += 1
            elif op in {"c", "qu"}:
                curve_count += 1
    if primitive_count == 0:
        page_rect = page.rect
        x0, y0, x1, y1 = page_rect.x0, page_rect.y0, page_rect.x1, page_rect.y1
    return {
        "x0": None if x0 == inf else x0,
        "y0": None if y0 == inf else y0,
        "x1": None if x1 == -inf else x1,
        "y1": None if y1 == -inf else y1,
        "primitive_count": primitive_count,
        "line_count": line_count,
        "curve_count": curve_count,
        "rect_count": rect_count,
        "layer_name": None,
        "color": None,
        "source": "pymupdf",
    }
