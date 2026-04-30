from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ManualRegion:
    page_id: int
    x0: float
    y0: float
    x1: float
    y1: float
    raw_text: str = ""
    evidence_crop_path: str | None = None
