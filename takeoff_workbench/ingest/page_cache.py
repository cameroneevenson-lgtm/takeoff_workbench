from __future__ import annotations

from pathlib import Path
from typing import Any


def cache_path_for_page(cache_dir: str | Path, document_id: int, page_number: int, suffix: str = ".png") -> Path:
    return Path(cache_dir) / "pages" / f"doc_{document_id}_page_{page_number}{suffix}"


def ensure_parent(path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    return out


def render_page_image(page: Any, path: str | Path, zoom: float = 1.0) -> str:
    import fitz

    out = ensure_parent(path)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    pix.save(str(out))
    return str(out)
