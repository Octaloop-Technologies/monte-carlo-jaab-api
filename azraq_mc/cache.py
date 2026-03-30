from __future__ import annotations

import hashlib
import json
from typing import Any

from azraq_mc.schemas import ShockArray, ShockPackSpec
from azraq_mc.shockpack import build_shock_array as _build_shock_array

_MAX_ENTRIES = 16
_store: dict[str, ShockArray] = {}


def _spec_fingerprint(spec: ShockPackSpec) -> str:
    d: dict[str, Any] = spec.model_dump(mode="json")
    raw = json.dumps(d, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def get_or_build_shock_array(spec: ShockPackSpec) -> ShockArray:
    """Reuse identical ShockPack definitions to avoid recomputing large scenario matrices."""
    key = _spec_fingerprint(spec)
    hit = _store.get(key)
    if hit is not None and hit.n_scenarios == spec.n_scenarios:
        return hit
    arr = _build_shock_array(spec)
    if len(_store) >= _MAX_ENTRIES:
        _store.clear()
    _store[key] = arr
    return arr


def clear_shock_cache() -> None:
    _store.clear()
