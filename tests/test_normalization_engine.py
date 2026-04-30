from __future__ import annotations

from takeoff_workbench.data import db
from takeoff_workbench.normalize.learned_rules import create_rule
from takeoff_workbench.normalize.normalization_engine import NormalizationEngine


def test_normalization_engine_applies_global_csv_rule():
    result = NormalizationEngine().normalize("1/8 ALUM PL 12 x 36", raw_shape_phrase="PL", parsed_unit="in")
    assert result.normalized_family == "Aluminum"
    assert result.normalized_shape == "Plate"
    assert result.normalized_unit == "in"
    assert result.status == "auto_normalized"


def test_client_rule_overrides_global_rule(tmp_path):
    db_path = tmp_path / "project.sqlite"
    db.init_db(db_path)
    create_rule(
        db_path,
        scope="global",
        rule_type="shape",
        raw_pattern=r"(?i)\bTS\b",
        normalized_value={"normalized_shape": "Tube Steel"},
    )
    create_rule(
        db_path,
        scope="client",
        client_name="ABC",
        rule_type="shape",
        raw_pattern=r"(?i)\bTS\b",
        normalized_value={"normalized_shape": "HSS Tube"},
    )
    result = NormalizationEngine(db_path=db_path, client_name="ABC").normalize("TS 2 x 2 x 1/4")
    assert result.normalized_shape == "HSS Tube"


def test_project_rule_overrides_client_rule(tmp_path):
    db_path = tmp_path / "project.sqlite"
    db.init_db(db_path)
    create_rule(
        db_path,
        scope="client",
        client_name="ABC",
        rule_type="shape",
        raw_pattern=r"(?i)\bTS\b",
        normalized_value={"normalized_shape": "Tube Steel"},
    )
    create_rule(
        db_path,
        scope="project",
        rule_type="shape",
        raw_pattern=r"(?i)\bTS\b",
        normalized_value={"normalized_shape": "Project Tube"},
    )
    result = NormalizationEngine(db_path=db_path, client_name="ABC").normalize("TS 2 x 2 x 1/4")
    assert result.normalized_shape == "Project Tube"
