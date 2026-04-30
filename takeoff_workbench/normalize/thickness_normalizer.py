from __future__ import annotations

from fractions import Fraction


def normalize_thickness(value: str | float | int | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace('"', "")
    if not text:
        return None
    try:
        if "/" in text:
            return float(Fraction(text.replace(" ", "")))
        return float(text)
    except ValueError:
        return None
