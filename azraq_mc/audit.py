from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_lock = threading.Lock()


def _default_db_path() -> Path:
    return Path(os.environ.get("AZRAQ_AUDIT_DB", "data/azraq_audit.sqlite3"))


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS simulation_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            run_kind TEXT NOT NULL,
            asset_id TEXT,
            portfolio_id TEXT,
            shockpack_id TEXT,
            assumption_set_id TEXT,
            seed INTEGER,
            n_scenarios INTEGER,
            created_at_utc TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            client_hint TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_run_id ON simulation_runs(run_id)")
    conn.commit()


def log_simulation_run(
    *,
    run_id: str,
    run_kind: str,
    payload: dict[str, Any],
    shockpack_id: str | None = None,
    assumption_set_id: str | None = None,
    asset_id: str | None = None,
    portfolio_id: str | None = None,
    seed: int | None = None,
    n_scenarios: int | None = None,
    client_hint: str | None = None,
    db_path: Path | None = None,
) -> None:
    """Append-only SQLite audit log (Postgres-compatible schema evolution later)."""
    path = db_path or _default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "run_id": run_id,
        "run_kind": run_kind,
        "asset_id": asset_id,
        "portfolio_id": portfolio_id,
        "shockpack_id": shockpack_id,
        "assumption_set_id": assumption_set_id,
        "seed": seed,
        "n_scenarios": n_scenarios,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "payload_json": json.dumps(payload, default=str),
        "client_hint": client_hint,
    }
    with _lock:
        conn = sqlite3.connect(str(path))
        try:
            _ensure_schema(conn)
            conn.execute(
                """
                INSERT INTO simulation_runs (
                    run_id, run_kind, asset_id, portfolio_id, shockpack_id,
                    assumption_set_id, seed, n_scenarios, created_at_utc, payload_json, client_hint
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    row["run_id"],
                    row["run_kind"],
                    row["asset_id"],
                    row["portfolio_id"],
                    row["shockpack_id"],
                    row["assumption_set_id"],
                    row["seed"],
                    row["n_scenarios"],
                    row["created_at_utc"],
                    row["payload_json"],
                    row["client_hint"],
                ),
            )
            conn.commit()
        finally:
            conn.close()


def fetch_recent_runs(limit: int = 50, db_path: Path | None = None) -> list[dict[str, Any]]:
    path = db_path or _default_db_path()
    if not path.exists():
        return []
    conn = sqlite3.connect(str(path))
    try:
        _ensure_schema(conn)
        cur = conn.execute(
            """
            SELECT run_id, run_kind, asset_id, portfolio_id, shockpack_id,
                   assumption_set_id, seed, n_scenarios, created_at_utc, client_hint
            FROM simulation_runs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()
