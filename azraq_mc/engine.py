from __future__ import annotations

import hashlib
import time
import uuid
from datetime import datetime, timezone

import numpy as np

from azraq_mc.attribution import factor_attribution_dscr_tail_regression
from azraq_mc.attribution_advanced import (
    downside_loss_from_cf,
    euler_covariance_shares,
    shapley_incremental_r2,
)
from azraq_mc.calibration_sources import materialize_shockpack_margins
from azraq_mc.cache import get_or_build_shock_array
from azraq_mc.cache_pipeline import (
    get_cached_impact,
    pipeline_cache_enabled,
    pipeline_impact_fingerprint,
    put_cached_impact,
)
from azraq_mc.impact import financial_impact
from azraq_mc.metrics import build_financial_metrics, build_full_stack_metrics
from azraq_mc.performance import apply_performance_profile
from azraq_mc.schemas import (
    AssetAssumptions,
    ExecutionMode,
    PerformanceProfile,
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
    include_advanced_attribution: bool = False,
    attribution_tail_fraction: float = 0.05,
    execution_mode: ExecutionMode = "adhoc_asset",
    user_id: str | None = None,
    layer_versions: dict[str, str] | None = None,
    performance_profile: PerformanceProfile | None = None,
    shockpack_catalog_entry_id: str | None = None,
) -> SimulationResult:
    t0 = time.perf_counter()
    shock_spec = apply_performance_profile(shock_spec, performance_profile)
    shock_spec, cal_trace = materialize_shockpack_margins(shock_spec)
    shocks = get_or_build_shock_array(shock_spec)

    cache_hit = False
    if pipeline_cache_enabled():
        pkey = pipeline_impact_fingerprint(shock_spec, asset)
        cached = get_cached_impact(pkey)
        if cached is not None:
            outcomes = cached
            cache_hit = True
        else:
            outcomes = financial_impact(
                shocks, asset, margins=shock_spec.margins, shock_spec=shock_spec
            )
            put_cached_impact(pkey, outcomes)
    else:
        outcomes = financial_impact(shocks, asset, margins=shock_spec.margins, shock_spec=shock_spec)

    dsra_drag = None
    if outcomes.extensions:
        dsra_drag = outcomes.extensions.get("waterfall_dsra_mean_annual")

    metrics = build_financial_metrics(
        outcomes.dscr,
        outcomes.irr,
        asset.financing.covenant_dscr,
        total_capex=outcomes.total_capex,
        ebitda=outcomes.ebitda,
        levered_cf=outcomes.levered_cf,
        nav_proxy_equity=outcomes.nav_proxy_equity,
        liquidity_runway_months=outcomes.liquidity_runway_months,
        waterfall_dsra_avg_drag=dsra_drag,
        structural_pd_from_dscr=True,
    )
    fs_metrics = None
    if outcomes.layer is not None and asset.full_stack is not None:
        fs_metrics = build_full_stack_metrics(
            outcomes.layer,
            full_stack_cfg=asset.full_stack,
        )

    attribution = None
    if include_attribution:
        z_attr = np.asarray(shocks.z, dtype=np.float64)
        if z_attr.ndim == 3:
            z_attr = np.mean(z_attr, axis=2)
        attribution = factor_attribution_dscr_tail_regression(
            z_attr,
            outcomes.dscr,
            shock_spec.factor_order,
            tail_fraction=attribution_tail_fraction,
            levered_cf=outcomes.levered_cf,
        )
        if include_advanced_attribution and attribution is not None:
            loss = downside_loss_from_cf(outcomes.levered_cf)
            euler = euler_covariance_shares(z_attr, loss, shock_spec.factor_order)
            n_perm = min(48, max(8, shock_spec.n_scenarios // 40))
            shap = shapley_incremental_r2(
                z_attr, loss, shock_spec.factor_order, n_perm=n_perm, seed=shock_spec.seed
            )
            attribution = attribution.model_copy(
                update={
                    "euler_risk_contributions": euler,
                    "shapley_risk_contributions": shap,
                }
            )

    rid = run_id or str(uuid.uuid4())
    lv = layer_versions or layer_versions_bundle()
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    ext = dict(outcomes.extensions or {})
    if pipeline_cache_enabled():
        ext["pipeline_cache_hit"] = cache_hit
        ext["pipeline_fingerprint"] = pipeline_impact_fingerprint(shock_spec, asset)

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
        layer_versions=lv,
        margin_calibration_trace=cal_trace,
        shockpack_catalog_entry_id=shockpack_catalog_entry_id,
        compute_time_ms=round(elapsed_ms, 2),
        performance_profile=performance_profile,
    )
    return SimulationResult(
        metadata=meta,
        metrics=metrics,
        attribution=attribution,
        full_stack=fs_metrics,
        extensions=ext if ext else None,
    )


def run_adhoc_asset_simulation_deterministic_run_id(
    shock_spec: ShockPackSpec,
    asset: AssetAssumptions,
    *,
    model_version: str = "azraq-mc-v1",
    include_attribution: bool = False,
    include_advanced_attribution: bool = False,
    user_id: str | None = None,
    layer_versions: dict[str, str] | None = None,
    performance_profile: PerformanceProfile | None = None,
    shockpack_catalog_entry_id: str | None = None,
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
        include_advanced_attribution=include_advanced_attribution,
        execution_mode="adhoc_asset",
        user_id=user_id,
        layer_versions=layer_versions,
        performance_profile=performance_profile,
        shockpack_catalog_entry_id=shockpack_catalog_entry_id,
    )
