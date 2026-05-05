from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def format_quantity(value: Any) -> str:
    """Display count quantities without a trailing decimal."""
    if value is None:
        return ""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
    else:
        text = str(value).strip()
        if not text or text.lower() in {"nan", "none", "<na>"}:
            return ""

    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError):
        return text

    if not number.is_finite():
        return ""
    if number == number.to_integral_value():
        return str(int(number))
    formatted = format(number.normalize(), "f")
    return formatted.rstrip("0").rstrip(".")
