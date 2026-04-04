from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone

import numpy as np

from azraq_mc.calibration_sources import materialize_shockpack_margins
from azraq_mc.cache import get_or_build_shock_array
from azraq_mc.impact import financial_impact
from azraq_mc.metrics import build_financial_metrics, distribution_summary
from azraq_mc.performance import apply_performance_profile
from azraq_mc.schemas import (
    AssetAssumptions,
    PerAssetMetrics,
    PerformanceProfile,
    PortfolioMetrics,
    PortfolioRunMetadata,
    PortfolioSimulationResult,
    ShockPackSpec,
)
from azraq_mc.versioning import layer_versions_bundle


def run_portfolio_joint_simulation(
    shock_spec: ShockPackSpec,
    portfolio_id: str,
    portfolio_assumption_set_id: str,
    assets: list[AssetAssumptions],
    *,
    model_version: str = "azraq-mc-v2-portfolio",
    run_id: str | None = None,
    progress: Callable[[int, int], None] | None = None,
    user_id: str | None = None,
    layer_versions: dict[str, str] | None = None,
    performance_profile: PerformanceProfile | None = None,
    shockpack_catalog_entry_id: str | None = None,
) -> PortfolioSimulationResult:
    """
    Mode 3 — joint simulation: every asset sees the same ShockPack realisations (same scenario index).
    """
    if len(assets) < 2:
        raise ValueError("portfolio simulation requires at least two assets")
    ids = [a.asset_id for a in assets]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate asset_id in portfolio")

    t0 = time.perf_counter()
    shock_spec = apply_performance_profile(shock_spec, performance_profile)
    shock_spec, cal_trace = materialize_shockpack_margins(shock_spec)
    shocks = get_or_build_shock_array(shock_spec)
    n = shock_spec.n_scenarios
    dscr_cols: list[np.ndarray] = []
    breach_cols: list[np.ndarray] = []
    cf_sum = np.zeros(n, dtype=np.float64)
    per_asset: list[PerAssetMetrics] = []

    revenues = np.array([a.base_revenue_annual for a in assets], dtype=np.float64)
    w = revenues / revenues.sum()
    hhi = float(np.sum(w**2))

    for j, a in enumerate(assets):
        out = financial_impact(shocks, a, margins=shock_spec.margins, shock_spec=shock_spec)
        dsra_drag = (out.extensions or {}).get("waterfall_dsra_mean_annual")
        metrics = build_financial_metrics(
            out.dscr,
            out.irr,
            a.financing.covenant_dscr,
            ebitda=out.ebitda,
            levered_cf=out.levered_cf,
            nav_proxy_equity=out.nav_proxy_equity,
            liquidity_runway_months=out.liquidity_runway_months,
            waterfall_dsra_avg_drag=dsra_drag,
            structural_pd_from_dscr=True,
        )
        per_asset.append(
            PerAssetMetrics(asset_id=a.asset_id, assumption_set_id=a.assumption_set_id, metrics=metrics)
        )
        dscr_cols.append(np.where(np.isfinite(out.dscr), out.dscr, np.nan))
        breach_cols.append((np.isfinite(out.dscr) & (out.dscr < a.financing.covenant_dscr)).astype(np.float64))
        cf_sum += out.levered_cf
        if progress is not None:
            progress(j + 1, len(assets))

    dscr_stack = np.column_stack(dscr_cols)
    min_dscr = np.nanmin(dscr_stack, axis=1)
    bmat = np.column_stack(breach_cols)
    counts = bmat.astype(np.int32).sum(axis=1)
    wbreach = float(np.mean(bmat @ w))
    p_any = float(np.mean(counts >= 1))
    p_at_least_k: dict[str, float] = {
        str(k): float(np.mean(counts >= k)) for k in range(2, len(assets) + 1)
    }

    p05_cf = float(np.percentile(cf_sum, 5))
    tail_cf = cf_sum[cf_sum <= p05_cf]
    cvar_cf = float(np.mean(tail_cf)) if tail_cf.size else None

    portfolio = PortfolioMetrics(
        n_assets=len(assets),
        scenarios=n,
        probability_any_covenant_breach=p_any,
        probability_at_least_k_breaches=p_at_least_k,
        min_dscr_across_assets=distribution_summary(min_dscr),
        sum_levered_cf_year1=distribution_summary(cf_sum),
        var_sum_levered_cf_p05=p05_cf,
        cvar_sum_levered_cf_p05=cvar_cf,
        revenue_herfindahl=hhi,
        weighted_covenant_breach_exposure=wbreach,
    )

    meta = PortfolioRunMetadata(
        run_id=run_id or str(uuid.uuid4()),
        portfolio_id=portfolio_id,
        assumption_set_id=portfolio_assumption_set_id,
        shockpack_id=shock_spec.shockpack_id,
        model_version=model_version,
        seed=shock_spec.seed,
        n_scenarios=shock_spec.n_scenarios,
        sampling_method=shock_spec.sampling_method,
        asset_ids=ids,
        created_at_utc=datetime.now(timezone.utc),
        execution_mode="portfolio_joint",
        user_id=user_id,
        layer_versions=layer_versions or layer_versions_bundle(),
        margin_calibration_trace=cal_trace,
        shockpack_catalog_entry_id=shockpack_catalog_entry_id,
        compute_time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
        performance_profile=performance_profile,
    )
    return PortfolioSimulationResult(metadata=meta, per_asset=per_asset, portfolio=portfolio)
