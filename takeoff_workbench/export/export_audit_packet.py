from __future__ import annotations

from pathlib import Path


def audit_packet_dir(db_path: str | Path) -> Path:
    return Path(db_path).resolve().parent / "_audit"
