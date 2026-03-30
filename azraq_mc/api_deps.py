from __future__ import annotations

import os

from fastapi import Header, HTTPException


def optional_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    expected = os.environ.get("AZRAQ_API_KEY")
    if not expected:
        return
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


def read_user_id(x_azraq_user_id: str | None = Header(default=None, alias="X-Azraq-User-Id")) -> str | None:
    return x_azraq_user_id or None
