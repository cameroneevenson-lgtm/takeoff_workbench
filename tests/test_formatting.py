from __future__ import annotations

from takeoff_workbench.formatting import format_quantity


def test_format_quantity_uses_integer_display_for_whole_counts():
    assert format_quantity(4.0) == "4"
    assert format_quantity("10.000") == "10"


def test_format_quantity_preserves_fractional_values_when_needed():
    assert format_quantity(2.5) == "2.5"
