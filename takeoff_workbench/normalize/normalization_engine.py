from __future__ import annotations

import csv
import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from takeoff_workbench.data import db


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@dataclass
class NormalizationResult:
    normalized_family: Optional[str] = None
    normalized_spec: Optional[str] = None
    normalized_shape: Optional[str] = None
    normalized_unit: Optional[str] = None
    confidence: float = 0.0
    status: str = "unresolved"
    rule_ids: list[str] = field(default_factory=list)

    def to_candidate_fields(self) -> dict[str, Any]:
        return {
            "normalized_family": self.normalized_family,
            "normalized_spec": self.normalized_spec,
            "normalized_shape": self.normalized_shape,
            "normalized_unit": self.normalized_unit,
            "normalization_confidence": self.confidence,
            "normalization_status": self.status,
            "normalization_rule_ids": ",".join(self.rule_ids),
        }


class NormalizationEngine:
    def __init__(
        self,
        *,
        db_path: str | Path | None = None,
        data_dir: str | Path | None = None,
        client_name: str | None = None,
    ) -> None:
        self.db_path = Path(db_path) if db_path else None
        self.data_dir = Path(data_dir) if data_dir else DATA_DIR
        self.client_name = client_name or "Default"

    def normalize(
        self,
        raw_text: str,
        *,
        raw_shape_phrase: str | None = None,
        parsed_unit: str | None = None,
    ) -> NormalizationResult:
        result = NormalizationResult()
        text = raw_text or ""

        self._apply_db_rules(result, text)
        self._apply_csv_material_rules(result, text)
        shape_text = raw_shape_phrase or text
        self._apply_csv_shape_rules(result, shape_text)
        unit_text = parsed_unit or text
        self._apply_csv_unit_rules(result, unit_text)

        if result.normalized_family or result.normalized_shape or result.normalized_unit:
            result.status = "auto_normalized"
            result.confidence = max(result.confidence, 0.1)
        return result

    def _db_rule_rows(self) -> list[sqlite3.Row]:
        if not self.db_path:
            return []
        db.init_db(self.db_path)
        with db.open_db(self.db_path) as conn:
            rows: list[sqlite3.Row] = []
            for scope, client in (
                ("project", None),
                ("client", self.client_name),
                ("global", None),
            ):
                if client:
                    found = conn.execute(
                        """
                        SELECT * FROM normalization_rules
                        WHERE active = 1 AND scope = ? AND client_name = ?
                        ORDER BY confidence DESC, id DESC
                        """,
                        (scope, client),
                    ).fetchall()
                else:
                    found = conn.execute(
                        """
                        SELECT * FROM normalization_rules
                        WHERE active = 1 AND scope = ?
                        ORDER BY confidence DESC, id DESC
                        """,
                        (scope,),
                    ).fetchall()
                rows.extend(found)
            return rows

    def _apply_db_rules(self, result: NormalizationResult, text: str) -> None:
        for row in self._db_rule_rows():
            pattern = row["raw_pattern"] or ""
            try:
                matched = re.search(pattern, text)
            except re.error:
                matched = None
            if not matched:
                continue
            try:
                payload = json.loads(row["normalized_value_json"] or "{}")
            except json.JSONDecodeError:
                payload = {}
            self._merge_result(result, payload, row["confidence"] or 0.0, f"db:{row['id']}")
            if self._has_rule_answer(result, row["rule_type"]):
                continue

    def _apply_csv_material_rules(self, result: NormalizationResult, text: str) -> None:
        for idx, row in enumerate(self._read_csv("material_aliases.csv"), start=1):
            if result.normalized_family and result.normalized_spec:
                return
            if not _matches(row.get("raw_pattern"), text):
                continue
            payload = {
                "normalized_family": row.get("normalized_family") or None,
                "normalized_spec": row.get("normalized_spec") or None,
            }
            self._merge_result(result, payload, _float(row.get("confidence")), f"csv:material:{idx}")

    def _apply_csv_shape_rules(self, result: NormalizationResult, text: str) -> None:
        if result.normalized_shape:
            return
        for idx, row in enumerate(self._read_csv("shape_aliases.csv"), start=1):
            if not _matches(row.get("raw_pattern"), text):
                continue
            payload = {"normalized_shape": row.get("normalized_shape") or None}
            self._merge_result(result, payload, _float(row.get("confidence")), f"csv:shape:{idx}")
            return

    def _apply_csv_unit_rules(self, result: NormalizationResult, text: str) -> None:
        if result.normalized_unit:
            return
        for idx, row in enumerate(self._read_csv("unit_aliases.csv"), start=1):
            if not _matches(row.get("raw_pattern"), text):
                continue
            payload = {"normalized_unit": row.get("normalized_unit") or None}
            self._merge_result(result, payload, 0.85, f"csv:unit:{idx}")
            return

    def _read_csv(self, name: str) -> list[dict[str, str]]:
        path = self.data_dir / name
        if not path.exists():
            return []
        with path.open("r", newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    @staticmethod
    def _has_rule_answer(result: NormalizationResult, rule_type: str | None) -> bool:
        rule_type = (rule_type or "").lower()
        if rule_type == "material":
            return bool(result.normalized_family or result.normalized_spec)
        if rule_type == "shape":
            return bool(result.normalized_shape)
        if rule_type == "unit":
            return bool(result.normalized_unit)
        return False

    @staticmethod
    def _merge_result(
        result: NormalizationResult,
        payload: dict[str, Any],
        confidence: float,
        rule_id: str,
    ) -> None:
        for key in ("normalized_family", "normalized_spec", "normalized_shape", "normalized_unit"):
            value = payload.get(key)
            if value and not getattr(result, key):
                setattr(result, key, value)
        result.confidence = max(result.confidence, confidence)
        result.rule_ids.append(rule_id)


def _matches(pattern: str | None, text: str) -> bool:
    if not pattern:
        return False
    try:
        return re.search(pattern, text or "") is not None
    except re.error:
        return False


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
