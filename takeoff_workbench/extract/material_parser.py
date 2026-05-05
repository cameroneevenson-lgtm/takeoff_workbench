from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from fractions import Fraction
from typing import Optional


NUMBER_RE = re.compile(r"(?<![A-Za-z0-9])(?:\d+\s*/\s*\d+|\d+\.\d+|\.\d+|\d+)(?![A-Za-z0-9])")
QTY_RE = re.compile(r"(?i)\b(?:QTY|QUANTITY)?\s*([0-9]+)\s*(?:EA|PCS|PC|X|-)?\b")
MATERIAL_PATTERNS = [
    (re.compile(r"(?i)\b5052[- ]?H32\b"), "5052-H32"),
    (re.compile(r"(?i)\bALUM(?:INUM)?\b|\bALUMINIUM\b|\bAL\b"), "ALUM"),
    (re.compile(r"(?i)\bM\.?S\.?\b"), "M.S."),
    (re.compile(r"(?i)\bSS\b"), "SS"),
]
SHAPE_PATTERNS = [
    (re.compile(r"(?i)\bHSS\b"), "HSS"),
    (re.compile(r"(?i)\bTS\b"), "TS"),
    (re.compile(r"(?i)\bPL(?:ATE)?\b"), "PL"),
    (re.compile(r"(?i)\bSHT\b"), "SHT"),
    (re.compile(r"(?i)\bFLAT\s+BAR\b"), "FLAT BAR"),
    (re.compile(r"(?i)\bFB\b"), "FB"),
    (re.compile(r"(?i)\bL\s*(?=\d)"), "L"),
]


@dataclass
class ParsedMaterial:
    raw_text: str
    raw_material_phrase: Optional[str] = None
    raw_shape_phrase: Optional[str] = None
    raw_dimension_phrase: Optional[str] = None
    parsed_quantity: Optional[float] = None
    parsed_unit: Optional[str] = "in"
    parsed_thickness: Optional[float] = None
    parsed_width: Optional[float] = None
    parsed_height: Optional[float] = None
    parsed_length: Optional[float] = None
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def parse_number(token: str) -> float:
    value = token.strip().replace(" ", "")
    if "/" in value:
        return float(Fraction(value))
    return float(value)


def _find_first(patterns: list[tuple[re.Pattern[str], str]], text: str) -> Optional[str]:
    for pattern, value in patterns:
        if pattern.search(text):
            return value
    return None


def _extract_quantity(text: str) -> Optional[float]:
    qty_match = re.search(r"(?i)\bQTY\s*([0-9]+)\b", text)
    if qty_match:
        return float(qty_match.group(1))
    leading = re.match(r"^\s*([0-9]+)\s*(?:EA|PCS|PC)\b", text, re.I)
    if leading:
        return float(leading.group(1))
    return None


def _table_item_quantity_prefix(text: str) -> tuple[Optional[float], str]:
    match = re.match(r"^\s*(?:ITEM\s*)?[A-Za-z]?\d+\s+([0-9]+)\s+(.+)$", text, re.I)
    if not match:
        return None, text
    remainder = match.group(2)
    if not (_find_first(MATERIAL_PATTERNS, remainder) or _find_first(SHAPE_PATTERNS, remainder)):
        return None, text
    return float(match.group(1)), remainder


def _dimension_text(text: str) -> str:
    tokens = NUMBER_RE.findall(text)
    return " x ".join(token.strip() for token in tokens)


def parse_material_candidate(text: str) -> ParsedMaterial:
    raw = " ".join(str(text or "").split())
    upper = raw.upper()
    parsed = ParsedMaterial(raw_text=raw)
    if not raw:
        return parsed

    parsed.parsed_quantity = _extract_quantity(raw)
    parse_text = raw
    prefix_quantity, prefix_remainder = _table_item_quantity_prefix(raw)
    if parsed.parsed_quantity is None and prefix_quantity is not None:
        parsed.parsed_quantity = prefix_quantity
        parse_text = prefix_remainder
    parsed.raw_material_phrase = _find_first(MATERIAL_PATTERNS, raw)
    parsed.raw_shape_phrase = _find_first(SHAPE_PATTERNS, raw)
    parsed.raw_dimension_phrase = _dimension_text(parse_text) or None

    if re.search(r"(?i)\b(?:GA|GAUGE)\b", raw):
        parsed.parsed_unit = "gauge"
    elif re.search(r"(?i)\bMM\b", raw):
        parsed.parsed_unit = "mm"
    else:
        parsed.parsed_unit = "in"

    numbers = [parse_number(token) for token in NUMBER_RE.findall(parse_text)]
    if parsed.parsed_quantity is not None and numbers and int(numbers[0]) == int(parsed.parsed_quantity):
        numbers = numbers[1:]

    if parsed.parsed_unit == "gauge":
        gauge = numbers[0] if numbers else None
        parsed.parsed_thickness = gauge
    elif parsed.raw_shape_phrase in {"HSS", "TS"}:
        if len(numbers) >= 1:
            parsed.parsed_width = numbers[0]
        if len(numbers) >= 2:
            parsed.parsed_height = numbers[1]
        if len(numbers) >= 3:
            parsed.parsed_thickness = numbers[2]
        if len(numbers) >= 4:
            parsed.parsed_length = numbers[3]
    elif parsed.raw_shape_phrase == "L":
        if len(numbers) >= 1:
            parsed.parsed_width = numbers[0]
        if len(numbers) >= 2:
            parsed.parsed_height = numbers[1]
        if len(numbers) >= 3:
            parsed.parsed_thickness = numbers[2]
    elif parsed.raw_shape_phrase in {"PL", "SHT"}:
        if len(numbers) >= 1:
            parsed.parsed_thickness = numbers[0]
        if len(numbers) >= 2:
            parsed.parsed_width = numbers[1]
        if len(numbers) >= 3:
            parsed.parsed_length = numbers[2]
    elif parsed.raw_shape_phrase in {"FLAT BAR", "FB"}:
        if len(numbers) >= 1:
            parsed.parsed_width = numbers[0]
        if len(numbers) >= 2:
            parsed.parsed_thickness = numbers[1]
        if len(numbers) >= 3:
            parsed.parsed_length = numbers[2]
    else:
        if len(numbers) >= 1:
            parsed.parsed_thickness = numbers[0]
        if len(numbers) >= 2:
            parsed.parsed_width = numbers[1]
        if len(numbers) >= 3:
            parsed.parsed_length = numbers[2]

    score = 0.15
    if parsed.raw_material_phrase:
        score += 0.25
    if parsed.raw_shape_phrase:
        score += 0.25
    if parsed.raw_dimension_phrase:
        score += 0.25
    if parsed.parsed_quantity is not None:
        score += 0.10
    if "MATERIAL" in upper or "QTY" in upper:
        score += 0.05
    parsed.confidence = min(score, 0.95)
    return parsed


def parse_material_text(text: str) -> dict:
    return parse_material_candidate(text).to_dict()
