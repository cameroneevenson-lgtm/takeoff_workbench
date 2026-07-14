from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from rendering.pdf_page_renderer import (
    PDF_VIEW_CACHE_LIMIT_BYTES,
    PDF_VIEW_DPI,
    RenderedPage,
    _render_pdf_page,
)


class PageRenderCache:
    """LRU-style cache of rendered PDF pages, evicted by a total byte-size ceiling.

    Extracted from ``TakeoffMainWindow``, which previously mixed cache
    bookkeeping (an ``OrderedDict`` plus a running byte total and an eviction
    loop) directly into its ``_render_page_cached``/``_evict_render_cache``
    instance methods. The window still owns viewport-size bucketing (that is
    a UI concern); this class only owns the cache/evict mechanics, keyed on
    the same ``(path, page_number, vw, vh, dpi)`` tuple as before.
    """

    def __init__(self, limit_bytes: int = PDF_VIEW_CACHE_LIMIT_BYTES) -> None:
        self._limit_bytes = limit_bytes
        self._entries: "OrderedDict[tuple[str, int, int, int, int], RenderedPage]" = OrderedDict()
        self._bytes = 0

    def get_or_render(self, pdf_path: Path, page_number: int, vw: int, vh: int) -> RenderedPage:
        key = (str(pdf_path.resolve()), page_number, vw, vh, PDF_VIEW_DPI)
        cached = self._entries.get(key)
        if cached is not None:
            self._entries.move_to_end(key)
            return cached
        rendered = _render_pdf_page(pdf_path, page_number, viewport_size=(vw, vh))
        self._entries[key] = rendered
        self._entries.move_to_end(key)
        self._bytes += rendered.bytes_estimate
        self._evict()
        return rendered

    def _evict(self) -> None:
        while self._bytes > self._limit_bytes and len(self._entries) > 1:
            _, old = self._entries.popitem(last=False)
            self._bytes = max(0, self._bytes - old.bytes_estimate)
