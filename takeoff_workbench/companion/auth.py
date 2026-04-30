from __future__ import annotations

import hmac
import os
from typing import Any

from flask import Request


def configured_token(explicit: str | None = None) -> str:
    return explicit if explicit is not None else os.environ.get("TAKEOFF_COMPANION_TOKEN", "")


def is_readonly(explicit: bool | None = None) -> bool:
    if explicit is not None:
        return explicit
    return os.environ.get("TAKEOFF_COMPANION_READONLY", "0").strip().lower() in {"1", "true", "yes", "on"}


def token_from_request(request: Request) -> str:
    header = request.headers.get("X-Takeoff-Token", "")
    if header:
        return header.strip()
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    if request.is_json:
        payload: Any = request.get_json(silent=True) or {}
        return str(payload.get("token") or "").strip()
    return str(request.form.get("token") or "").strip()


def write_allowed(request: Request, *, readonly: bool | None = None, token: str | None = None) -> tuple[bool, str]:
    if is_readonly(readonly):
        return False, "Companion is running in read-only mode."
    expected = configured_token(token)
    if not expected:
        return False, "TAKEOFF_COMPANION_TOKEN is not configured; write actions are disabled."
    supplied = token_from_request(request)
    if not supplied or not hmac.compare_digest(supplied, expected):
        return False, "Invalid or missing companion token."
    return True, ""
