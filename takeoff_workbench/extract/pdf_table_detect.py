from __future__ import annotations

TABLE_KEYWORDS = ("MATERIAL", "QTY", "DESCRIPTION", "LENGTH", "SIZE", "PART", "ITEM")


def likely_table_text(text: str) -> bool:
    upper = (text or "").upper()
    hits = sum(1 for keyword in TABLE_KEYWORDS if keyword in upper)
    return hits >= 2
