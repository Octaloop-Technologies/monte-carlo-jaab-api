from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import TypeAdapter

from azraq_mc.schemas import BaseCaseResult, PortfolioSimulationResult, SavedSnapshot, SimulationResult


def _safe_slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", text).strip("_") or "snapshot"

JsonDict = dict[str, Any]


def save_snapshot(
    root: Path | str,
    kind: Literal["asset_simulation", "portfolio_simulation", "v0_base"],
    body: SimulationResult | PortfolioSimulationResult | BaseCaseResult,
    *,
    label: str | None = None,
) -> Path:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = _safe_slug(label or getattr(body.metadata, "run_id", "run"))
    path = root / f"{kind}_{stamp}_{name}.json"

    snap = SavedSnapshot(kind=kind, label=label, body=body.model_dump(mode="json"))
    path.write_text(snap.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_snapshot_raw(path: Path | str) -> SavedSnapshot:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return SavedSnapshot.model_validate(data)


def load_snapshot_typed(
    path: Path | str,
) -> SimulationResult | PortfolioSimulationResult | BaseCaseResult:
    snap = load_snapshot_raw(path)
    if snap.kind == "asset_simulation":
        return TypeAdapter(SimulationResult).validate_python(snap.body)
    if snap.kind == "portfolio_simulation":
        return TypeAdapter(PortfolioSimulationResult).validate_python(snap.body)
    if snap.kind == "v0_base":
        return TypeAdapter(BaseCaseResult).validate_python(snap.body)
    raise ValueError(f"unknown snapshot kind: {snap.kind}")


def list_snapshots(root: Path | str) -> list[Path]:
    p = Path(root)
    if not p.exists():
        return []
    return sorted(p.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)


def metrics_delta(a: JsonDict, b: JsonDict, *, prefix: str = "") -> JsonDict:
    """Shallow diff for nested metric dicts (best-effort for dashboards)."""
    out: JsonDict = {}
    if isinstance(a, dict) and isinstance(b, dict):
        keys = set(a) | set(b)
        for k in sorted(keys):
            ka = a.get(k)
            kb = b.get(k)
            pfx = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(ka, dict) and isinstance(kb, dict):
                out.update(metrics_delta(ka, kb, prefix=pfx))
            elif isinstance(ka, (int, float)) and isinstance(kb, (int, float)) and ka != kb:
                out[pfx] = {"before": ka, "after": kb, "delta": kb - ka}
    return out


def diff_simulation_results(
    before: SimulationResult,
    after: SimulationResult,
) -> dict[str, Any]:
    return metrics_delta(
        before.metrics.model_dump(mode="json"),
        after.metrics.model_dump(mode="json"),
    )
