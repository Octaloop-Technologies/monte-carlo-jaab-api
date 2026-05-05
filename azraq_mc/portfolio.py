from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone

import numpy as np

from azraq_mc.calibration_sources import materialize_shockpack_margins
from azraq_mc.cache import get_or_build_shock_array
from azraq_mc.impact import financial_impact
from azraq_mc.metrics import build_financial_metrics, distribution_summary, var_cvar_irr
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


def _pairwise_pearson_columns(X: np.ndarray) -> np.ndarray:
    """Pearson correlation between columns of X (n_samples × n_assets). Diagonal = 1."""
    _, n = X.shape
    out = np.eye(n, dtype=np.float64)
    for i in range(n):
        for j in range(i + 1, n):
            xi = X[:, i]
            xj = X[:, j]
            mask = np.isfinite(xi) & np.isfinite(xj)
            if mask.sum() < 3:
                r = np.nan
            else:
                a = xi[mask]
                b = xj[mask]
                if np.std(a) < 1e-14 or np.std(b) < 1e-14:
                    r = np.nan
                else:
                    r = float(np.corrcoef(a, b)[0, 1])
            out[i, j] = out[j, i] = r
    return out


def _row_weighted_mean(X: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Per Monte Carlo row: Σᵢ xᵢ wᵢ / Σᵢ wᵢ over finite xᵢ only (same w as HHI / weighted breach)."""
    X = np.asarray(X, dtype=np.float64)
    w = np.asarray(w, dtype=np.float64).reshape(1, -1)
    ok = np.isfinite(X)
    w_eff = np.where(ok, w, 0.0)
    den = np.sum(w_eff, axis=1)
    num = np.sum(np.where(ok, X * w, 0.0), axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 1e-15, num / den, np.nan)


def _corr_matrix_jsonable(M: np.ndarray) -> list[list[float | None]]:
    """JSON-safe symmetric matrix: NaN -> None, ~round for stability."""
    rows: list[list[float | None]] = []
    for i in range(M.shape[0]):
        row: list[float | None] = []
        for j in range(M.shape[1]):
            x = M[i, j]
            if not np.isfinite(x):
                row.append(None)
            else:
                row.append(float(round(x, 6)))
        rows.append(row)
    return rows


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
    irr_cols: list[np.ndarray] = []
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
            total_capex=out.total_capex,
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
        irr_cols.append(np.where(np.isfinite(out.irr), out.irr, np.nan))
        breach_cols.append((np.isfinite(out.dscr) & (out.dscr < a.financing.covenant_dscr)).astype(np.float64))
        cf_sum += out.levered_cf
        if progress is not None:
            progress(j + 1, len(assets))

    dscr_stack = np.column_stack(dscr_cols)
    min_dscr = np.nanmin(dscr_stack, axis=1)
    max_dscr = np.nanmax(dscr_stack, axis=1)
    blend_dscr = _row_weighted_mean(dscr_stack, w)

    irr_stack = np.column_stack(irr_cols)
    blend_irr = _row_weighted_mean(irr_stack, w)
    irr_var, irr_cvar = var_cvar_irr(blend_irr)

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

    corr_dscr = _corr_matrix_jsonable(_pairwise_pearson_columns(dscr_stack))
    corr_irr = _corr_matrix_jsonable(_pairwise_pearson_columns(irr_stack))

    portfolio = PortfolioMetrics(
        n_assets=len(assets),
        scenarios=n,
        probability_any_covenant_breach=p_any,
        probability_at_least_k_breaches=p_at_least_k,
        min_dscr_across_assets=distribution_summary(min_dscr),
        max_dscr_across_assets=distribution_summary(max_dscr),
        revenue_weighted_mean_dscr_across_assets=distribution_summary(blend_dscr),
        revenue_weighted_mean_equity_irr_across_assets=distribution_summary(blend_irr),
        var_irr_95=irr_var,
        cvar_irr_95=irr_cvar,
        sum_levered_cf_year1=distribution_summary(cf_sum),
        var_sum_levered_cf_p05=p05_cf,
        cvar_sum_levered_cf_p05=cvar_cf,
        revenue_herfindahl=hhi,
        weighted_covenant_breach_exposure=wbreach,
        cross_asset_dscr_correlation_pearson=corr_dscr,
        cross_asset_equity_irr_correlation_pearson=corr_irr,
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
        factor_order=list(shock_spec.factor_order),
        factor_correlation=shock_spec.correlation,
        copula=str(shock_spec.copula),
    )
    return PortfolioSimulationResult(metadata=meta, per_asset=per_asset, portfolio=portfolio)
