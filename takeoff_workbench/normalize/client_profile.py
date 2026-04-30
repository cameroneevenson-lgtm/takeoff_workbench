from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClientProfile:
    name: str = "Default"
    notes: str = ""


DEFAULT_PROFILE = ClientProfile()
