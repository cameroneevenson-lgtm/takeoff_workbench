from __future__ import annotations

import pytest

from takeoff_workbench.extract.material_parser import parse_material_text


@pytest.mark.parametrize(
    ("text", "shape", "thickness", "width", "height", "length", "unit"),
    [
        ("QTY 4 - 1/8 ALUM PL 12 x 36", "PL", 0.125, 12.0, None, 36.0, "in"),
        ("HSS 2 x 2 x 1/4", "HSS", 0.25, 2.0, 2.0, None, "in"),
        ("L 3 x 3 x 1/4", "L", 0.25, 3.0, 3.0, None, "in"),
        ("10 GA SHT", "SHT", 10.0, None, None, None, "gauge"),
        ("M.S. FLAT BAR 2 x 1/4", "FLAT BAR", 0.25, 2.0, None, None, "in"),
    ],
)
def test_material_parser_examples(text, shape, thickness, width, height, length, unit):
    parsed = parse_material_text(text)
    assert parsed["raw_shape_phrase"] == shape
    assert parsed["parsed_unit"] == unit
    assert parsed["parsed_thickness"] == pytest.approx(thickness)
    if width is None:
        assert parsed["parsed_width"] is None
    else:
        assert parsed["parsed_width"] == pytest.approx(width)
    if height is None:
        assert parsed["parsed_height"] is None
    else:
        assert parsed["parsed_height"] == pytest.approx(height)
    if length is None:
        assert parsed["parsed_length"] is None
    else:
        assert parsed["parsed_length"] == pytest.approx(length)


def test_material_parser_quantity_and_material():
    parsed = parse_material_text("QTY 4 - 1/8 ALUM PL 12 x 36")
    assert parsed["parsed_quantity"] == 4
    assert parsed["raw_material_phrase"] == "ALUM"
    assert parsed["confidence"] > 0.5
