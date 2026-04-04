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


def read_tenant_id(x_azraq_tenant_id: str | None = Header(default=None, alias="X-Azraq-Tenant-Id")) -> str | None:
    return x_azraq_tenant_id or None


def require_catalog_promoter(
    x_azraq_catalog_role: str | None = Header(default=None, alias="X-Azraq-Catalog-Role"),
) -> None:
    """
    Promotion requires a role in AZRAQ_CATALOG_PROMOTER_ROLES (comma-separated), default admin,promoter.
    If the env var is empty, promotion is allowed without role (local dev).
    """
    raw = os.environ.get("AZRAQ_CATALOG_PROMOTER_ROLES", "admin,promoter")
    allowed = [x.strip() for x in raw.split(",") if x.strip()]
    if not allowed:
        return
    if not x_azraq_catalog_role or x_azraq_catalog_role not in allowed:
        raise HTTPException(
            status_code=403,
            detail="Set X-Azraq-Catalog-Role to an allowed promoter role",
        )
