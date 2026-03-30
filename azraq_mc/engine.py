from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

import numpy as np

from azraq_mc.attribution import factor_attribution_dscr_tail_regression
from azraq_mc.cache import get_or_build_shock_array
from azraq_mc.impact import financial_impact
from azraq_mc.metrics import build_financial_metrics, build_full_stack_metrics
from azraq_mc.schemas import (
    AssetAssumptions,
    ExecutionMode,
    ShockPackSpec,
    SimulationResult,
    SimulationRunMetadata,
)
from azraq_mc.versioning import layer_versions_bundle


def _run_id_from_inputs(shockpack_id: str, assumption_set_id: str, seed: int, n: int) -> str:
    h = hashlib.sha256(f"{shockpack_id}|{assumption_set_id}|{seed}|{n}".encode()).hexdigest()[:12]
    return f"run-{h}"


def run_adhoc_asset_simulation(
    shock_spec: ShockPackSpec,
    asset: AssetAssumptions,
    *,
    model_version: str = "azraq-mc-v1",
    run_id: str | None = None,
    include_attribution: bool = False,
    attribution_tail_fraction: float = 0.05,
    execution_mode: ExecutionMode = "adhoc_asset",
    user_id: str | None = None,
    layer_versions: dict[str, str] | None = None,
) -> SimulationResult:
    """
    Mode 1 — ad-hoc single-asset simulation: one ShockPack, one assumption set, vectorized impact.
    """
    shocks = get_or_build_shock_array(shock_spec)
    outcomes = financial_impact(shocks, asset, margins=shock_spec.margins)
    metrics = build_financial_metrics(
        outcomes.dscr,
        outcomes.irr,
        asset.financing.covenant_dscr,
    )
    fs_metrics = build_full_stack_metrics(outcomes.layer) if outcomes.layer is not None else None

    attribution = None
    if include_attribution:
        attribution = factor_attribution_dscr_tail_regression(
            np.asarray(shocks.z, dtype=np.float64),
            outcomes.dscr,
            shock_spec.factor_order,
            tail_fraction=attribution_tail_fraction,
        )

    rid = run_id or str(uuid.uuid4())
    meta = SimulationRunMetadata(
        run_id=rid,
        shockpack_id=shock_spec.shockpack_id,
        assumption_set_id=asset.assumption_set_id,
        asset_id=asset.asset_id,
        model_version=model_version,
        seed=shock_spec.seed,
        n_scenarios=shock_spec.n_scenarios,
        sampling_method=shock_spec.sampling_method,
        created_at_utc=datetime.now(timezone.utc),
        execution_mode=execution_mode,
        user_id=user_id,
        layer_versions=layer_versions or layer_versions_bundle(),
    )
    return SimulationResult(metadata=meta, metrics=metrics, attribution=attribution, full_stack=fs_metrics)


def run_adhoc_asset_simulation_deterministic_run_id(
    shock_spec: ShockPackSpec,
    asset: AssetAssumptions,
    *,
    model_version: str = "azraq-mc-v1",
    include_attribution: bool = False,
    user_id: str | None = None,
    layer_versions: dict[str, str] | None = None,
) -> SimulationResult:
    rid = _run_id_from_inputs(
        shock_spec.shockpack_id,
        asset.assumption_set_id,
        shock_spec.seed,
        shock_spec.n_scenarios,
    )
    return run_adhoc_asset_simulation(
        shock_spec,
        asset,
        model_version=model_version,
        run_id=rid,
        include_attribution=include_attribution,
        execution_mode="adhoc_asset",
        user_id=user_id,
        layer_versions=layer_versions,
    )
