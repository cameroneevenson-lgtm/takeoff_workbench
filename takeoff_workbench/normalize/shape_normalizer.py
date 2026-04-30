from __future__ import annotations

from takeoff_workbench.normalize.normalization_engine import NormalizationEngine, NormalizationResult


def normalize_shape(text: str, *, db_path: str | None = None, client_name: str | None = None) -> NormalizationResult:
    return NormalizationEngine(db_path=db_path, client_name=client_name).normalize(text, raw_shape_phrase=text)
