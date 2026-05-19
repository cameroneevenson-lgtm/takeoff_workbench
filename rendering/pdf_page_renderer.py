from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz
from PySide6.QtGui import QImage, QPixmap


PDF_VIEW_DPI = 500
PDF_VIEW_OVERSAMPLE = 2.0
PDF_VIEW_CACHE_BUCKET_PX = 160
PDF_VIEW_CACHE_LIMIT_BYTES = 1024 * 1024 * 1024


@dataclass
class RenderedPage:
    pixmap: QPixmap
    page_width: float
    page_height: float
    render_scale: float
    bytes_estimate: int


def _bucket_px(value: int) -> int:
    bucket = PDF_VIEW_CACHE_BUCKET_PX
    return ((max(1, int(value)) + bucket - 1) // bucket) * bucket


def _render_pdf_page(
    pdf_path: Path,
    page_number: int,
    *,
    viewport_size: tuple[int, int],
    dpi: int = PDF_VIEW_DPI,
    oversample: float = PDF_VIEW_OVERSAMPLE,
) -> RenderedPage:
    with fitz.open(str(pdf_path)) as doc:
        page = doc.load_page(page_number - 1)
        page_width = float(page.rect.width)
        page_height = float(page.rect.height)
        vw, vh = viewport_size
        fit_scale = min(max(vw, 1) / max(page_width, 1.0), max(vh, 1) / max(page_height, 1.0))
        render_scale = max(0.2, fit_scale * max(1.0, oversample))
        render_scale = min(render_scale, max(72.0, float(dpi)) / 72.0)
        try:
            fitz.TOOLS.set_graphics_min_line_width(1.0)
        except Exception:
            pass
        pix = page.get_pixmap(matrix=fitz.Matrix(render_scale, render_scale), alpha=False)
        image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
    pixmap = QPixmap.fromImage(image)
    return RenderedPage(
        pixmap=pixmap,
        page_width=page_width,
        page_height=page_height,
        render_scale=render_scale,
        bytes_estimate=max(1, image.sizeInBytes()) + max(1, pixmap.width() * pixmap.height() * 4),
    )
