from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from takeoff_workbench.data import db


def create_rule(
    db_path: str | Path,
    *,
    scope: str,
    rule_type: str,
    raw_pattern: str,
    normalized_value: Mapping[str, Any],
    client_name: str | None = None,
    confidence: float = 0.95,
    created_by: str = "local",
) -> int:
    db.init_db(db_path)
    with db.open_db(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO normalization_rules(
                scope, client_name, rule_type, raw_pattern, normalized_value_json,
                confidence, created_by, created_at, last_used_at, use_count, active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, 1)
            """,
            (
                scope,
                client_name,
                rule_type,
                raw_pattern,
                json.dumps(dict(normalized_value), sort_keys=True),
                confidence,
                created_by,
                db.utc_now(),
            ),
        )
        return int(cur.lastrowid)
