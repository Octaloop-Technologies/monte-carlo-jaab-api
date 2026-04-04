"""§6.2 — Optional full-stack cache: Z core + margins + asset economics fingerprint → outcomes blob."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from azraq_mc.cache import z_core_fingerprint
from azraq_mc.schemas import AssetAssumptions, ShockPackSpec

_MAX = 16
_store: dict[str, Any] = {}


def _asset_econ_dict(asset: AssetAssumptions) -> dict[str, Any]:
    return {
        "asset_id": asset.asset_id,
        "assumption_set_id": asset.assumption_set_id,
        "horizon_years": asset.horizon_years,
        "financing": asset.financing.model_dump(mode="json"),
        "equity_fraction": asset.equity_fraction,
        "tax_rate": asset.tax_rate,
        "base_revenue_annual": asset.base_revenue_annual,
        "base_opex_annual": asset.base_opex_annual,
        "initial_capex": asset.initial_capex,
        "utility_opex_annual": asset.utility_opex_annual,
        "factor_transforms": asset.factor_transforms.model_dump(mode="json")
        if asset.factor_transforms
        else None,
        "full_stack": asset.full_stack.model_dump(mode="json") if asset.full_stack else None,
        "waterfall": asset.waterfall.model_dump(mode="json") if asset.waterfall else None,
        "liquidity": asset.liquidity.model_dump(mode="json") if asset.liquidity else None,
    }


def pipeline_impact_fingerprint(spec: ShockPackSpec, asset: AssetAssumptions) -> str:
    payload = {
        "z": z_core_fingerprint(spec),
        "margins": spec.margins.model_dump(mode="json"),
        "macro": spec.macro_term_structure.model_dump(mode="json") if spec.macro_term_structure else None,
        "inflation": spec.inflation_process.model_dump(mode="json") if spec.inflation_process else None,
        "factor_order": list(spec.factor_order),
        "asset_econ": _asset_econ_dict(asset),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def pipeline_cache_enabled() -> bool:
    import os

    return os.environ.get("AZRAQ_PIPELINE_CACHE", "").strip().lower() in ("1", "true", "yes")


def get_cached_impact(key: str):
    return _store.get(key)


def put_cached_impact(key: str, value: Any) -> None:
    if len(_store) >= _MAX:
        _store.clear()
    _store[key] = value


def clear_pipeline_cache() -> None:
    _store.clear()
