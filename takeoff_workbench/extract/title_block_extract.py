from __future__ import annotations


def extract_title_block_hint(text: str) -> dict:
    upper = (text or "").upper()
    return {
        "has_title_block_terms": any(term in upper for term in ("DRAWN", "REV", "SCALE", "SHEET")),
    }
