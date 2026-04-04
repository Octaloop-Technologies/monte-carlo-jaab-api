from __future__ import annotations

import hashlib
import json
from typing import Any

from azraq_mc.schemas import ShockArray, ShockPackSpec
from azraq_mc.shockpack import generate_correlated_z_paths

_MAX_ENTRIES = 32
# Layer 1: correlated Z only (margins / dynamic_margins / macro_regime excluded → same Z reused)
_z_store: dict[str, np.ndarray] = {}


def _z_core_dict(spec: ShockPackSpec) -> dict[str, Any]:
    tg = spec.time_grid.model_dump(mode="json") if spec.time_grid else None
    return {
        "shockpack_id": spec.shockpack_id,
        "schema_version": spec.schema_version,
        "seed": spec.seed,
        "n_scenarios": spec.n_scenarios,
        "sampling_method": spec.sampling_method,
        "factor_order": list(spec.factor_order),
        "correlation": spec.correlation,
        "copula": spec.copula,
        "t_degrees_freedom": spec.t_degrees_freedom,
        "time_grid": tg,
    }


def z_core_fingerprint(spec: ShockPackSpec) -> str:
    raw = json.dumps(_z_core_dict(spec), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def get_or_build_z_core(spec: ShockPackSpec) -> np.ndarray:
    """§6.2 — Reuse Z when only margins / financing / macro_regime label change."""
    key = z_core_fingerprint(spec)
    hit = _z_store.get(key)
    if hit is not None and hit.shape[0] == spec.n_scenarios:
        return hit
    z = generate_correlated_z_paths(spec)
    if len(_z_store) >= _MAX_ENTRIES:
        _z_store.clear()
    _z_store[key] = z
    return z


def get_or_build_shock_array(spec: ShockPackSpec) -> ShockArray:
    """
    Prefer layered Z cache (§6.2), then wrap in ShockArray.
    `spec` must be the materialised spec (margins already resolved if dynamic).
    """
    z = get_or_build_z_core(spec)
    n_periods = int(z.shape[2]) if z.ndim == 3 else 1
    return ShockArray(
        shockpack_id=spec.shockpack_id,
        seed=spec.seed,
        n_scenarios=spec.n_scenarios,
        factor_order=spec.factor_order,
        n_periods=n_periods,
        z=z,
    )


def clear_shock_cache() -> None:
    _z_store.clear()
