from __future__ import annotations

from pathlib import Path


def find_pdfs(path: str | Path) -> list[Path]:
    root = Path(path)
    if root.is_file() and root.suffix.lower() == ".pdf":
        return [root]
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*.pdf") if p.is_file())
