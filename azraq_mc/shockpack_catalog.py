"""§6.3 — ShockPack artefact registry (SQLite) with promotion tiers, content hash, optional object store."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from azraq_mc.schemas import ShockPackSpec

PromotionTier = Literal["dev", "staging", "prod"]
PROMOTION_TIERS = ("dev", "staging", "prod")


def _default_catalog_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "shockpack_catalog.sqlite3"


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS shockpack_entries (
            entry_id TEXT PRIMARY KEY,
            shockpack_id TEXT NOT NULL,
            semver TEXT NOT NULL DEFAULT '1.0.0',
            tenant_id TEXT,
            spec_json TEXT NOT NULL,
            signature TEXT,
            created_at_utc TEXT NOT NULL,
            macro_regime TEXT,
            promotion_tier TEXT DEFAULT 'dev',
            content_sha256 TEXT,
            object_uri TEXT,
            rbac_owner_role TEXT DEFAULT 'editor'
        )
        """
    )
    cols = {row[1] for row in conn.execute("PRAGMA table_info(shockpack_entries)").fetchall()}
    migrations = [
        ("promotion_tier", "ALTER TABLE shockpack_entries ADD COLUMN promotion_tier TEXT DEFAULT 'dev'"),
        ("content_sha256", "ALTER TABLE shockpack_entries ADD COLUMN content_sha256 TEXT"),
        ("object_uri", "ALTER TABLE shockpack_entries ADD COLUMN object_uri TEXT"),
        ("rbac_owner_role", "ALTER TABLE shockpack_entries ADD COLUMN rbac_owner_role TEXT DEFAULT 'editor'"),
    ]
    for name, ddl in migrations:
        if name not in cols:
            conn.execute(ddl)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_spk ON shockpack_entries(shockpack_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tenant ON shockpack_entries(tenant_id)")
    conn.commit()


def _persist_object_store(entry_id: str, tenant_id: str | None, spec_json: str) -> str | None:
    root = os.environ.get("AZRAQ_ARTEFACT_ROOT")
    if not root or not tenant_id:
        return None
    d = Path(root) / tenant_id
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{entry_id}.json"
    path.write_text(spec_json, encoding="utf-8")
    return str(path.resolve())


def register_spec(
    spec: ShockPackSpec,
    *,
    semver: str = "1.0.0",
    tenant_id: str | None = None,
    signature: str | None = None,
    promotion_tier: PromotionTier = "dev",
    rbac_owner_role: str = "editor",
    db_path: Path | None = None,
) -> str:
    entry_id = str(uuid.uuid4())
    path = db_path or _default_catalog_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    spec_json = json.dumps(spec.model_dump(mode="json"), sort_keys=True)
    digest = hashlib.sha256(spec_json.encode()).hexdigest()
    object_uri = _persist_object_store(entry_id, tenant_id, spec_json)
    conn = sqlite3.connect(str(path))
    try:
        _ensure_schema(conn)
        conn.execute(
            """INSERT INTO shockpack_entries
            (entry_id, shockpack_id, semver, tenant_id, spec_json, signature, created_at_utc,
             macro_regime, promotion_tier, content_sha256, object_uri, rbac_owner_role)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry_id,
                spec.shockpack_id,
                semver,
                tenant_id,
                spec_json,
                signature,
                datetime.now(timezone.utc).isoformat(),
                spec.macro_regime,
                promotion_tier,
                digest,
                object_uri,
                rbac_owner_role,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return entry_id


def promote_entry(
    entry_id: str,
    to_tier: PromotionTier,
    *,
    db_path: Path | None = None,
) -> None:
    if to_tier not in PROMOTION_TIERS:
        raise ValueError(f"promotion tier must be one of {PROMOTION_TIERS}")
    path = db_path or _default_catalog_path()
    if not path.is_file():
        raise FileNotFoundError(f"catalog not found: {path}")
    conn = sqlite3.connect(str(path))
    try:
        _ensure_schema(conn)
        cur = conn.execute(
            "UPDATE shockpack_entries SET promotion_tier = ? WHERE entry_id = ?",
            (to_tier, entry_id),
        )
        if cur.rowcount == 0:
            raise KeyError(f"unknown catalog entry {entry_id!r}")
        conn.commit()
    finally:
        conn.close()


def load_entry(
    entry_id: str,
    *,
    tenant_id: str | None = None,
    enforce_tenant: bool = False,
    db_path: Path | None = None,
) -> dict[str, Any]:
    path = db_path or _default_catalog_path()
    if not path.is_file():
        raise FileNotFoundError(f"catalog not found: {path}")
    conn = sqlite3.connect(str(path))
    try:
        _ensure_schema(conn)
        row = conn.execute(
            "SELECT entry_id, shockpack_id, semver, tenant_id, spec_json, signature, created_at_utc, "
            "macro_regime, promotion_tier, content_sha256, object_uri, rbac_owner_role "
            "FROM shockpack_entries WHERE entry_id = ?",
            (entry_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise KeyError(f"unknown catalog entry {entry_id!r}")
    if enforce_tenant and tenant_id and row[3] and row[3] != tenant_id:
        raise PermissionError("catalog entry tenant does not match caller")
    return {
        "entry_id": row[0],
        "shockpack_id": row[1],
        "semver": row[2],
        "tenant_id": row[3],
        "spec": json.loads(row[4]),
        "signature": row[5],
        "created_at_utc": row[6],
        "macro_regime": row[7],
        "promotion_tier": row[8] if len(row) > 8 else "dev",
        "content_sha256": row[9] if len(row) > 9 else None,
        "object_uri": row[10] if len(row) > 10 else None,
        "rbac_owner_role": row[11] if len(row) > 11 else "editor",
    }


def list_entries(
    limit: int = 100,
    *,
    tenant_id: str | None = None,
    promotion_tier: PromotionTier | None = None,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    path = db_path or _default_catalog_path()
    if not path.is_file():
        return []
    conn = sqlite3.connect(str(path))
    try:
        _ensure_schema(conn)
        q = (
            "SELECT entry_id, shockpack_id, semver, tenant_id, created_at_utc, macro_regime, "
            "promotion_tier, content_sha256 FROM shockpack_entries WHERE 1=1"
        )
        args: list[Any] = []
        if tenant_id:
            q += " AND (tenant_id IS NULL OR tenant_id = ?)"
            args.append(tenant_id)
        if promotion_tier:
            q += " AND promotion_tier = ?"
            args.append(promotion_tier)
        q += " ORDER BY created_at_utc DESC LIMIT ?"
        args.append(limit)
        rows = conn.execute(q, args).fetchall()
    finally:
        conn.close()
    return [
        {
            "entry_id": r[0],
            "shockpack_id": r[1],
            "semver": r[2],
            "tenant_id": r[3],
            "created_at_utc": r[4],
            "macro_regime": r[5],
            "promotion_tier": r[6],
            "content_sha256": r[7],
        }
        for r in rows
    ]
