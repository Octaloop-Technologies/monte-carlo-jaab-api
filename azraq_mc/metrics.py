from __future__ import annotations

import numpy as np

from azraq_mc.full_stack_pipeline import LayerDiagnostics, milestone_completion_curve
from azraq_mc.cashflow_waterfall import structural_equity_pd_proxy
from azraq_mc.schemas import DistributionSummary, FinancialRiskMetrics, FullStackLayerConfig, FullStackMetrics


def _finite_summary(x: np.ndarray) -> DistributionSummary:
    v = np.asarray(x, dtype=np.float64)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return DistributionSummary(
            p05=0.0, p10=0.0, p50=0.0, p90=0.0, p95=0.0, mean=0.0, std=0.0
        )
    return DistributionSummary(
        p05=float(np.percentile(v, 5)),
        p10=float(np.percentile(v, 10)),
        p50=float(np.percentile(v, 50)),
        p90=float(np.percentile(v, 90)),
        p95=float(np.percentile(v, 95)),
        mean=float(np.mean(v)),
        std=float(np.std(v)),
    )


def var_cvar_level(v: np.ndarray, alpha: float = 0.05) -> tuple[float | None, float | None]:
    """Downside width vs median at alpha tail on levels (EBITDA, CF, NAV)."""
    arr = np.asarray(v, dtype=np.float64)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return None, None
    q = float(np.percentile(arr, alpha * 100))
    med = float(np.percentile(arr, 50))
    var = med - q
    tail = arr[arr <= q]
    cvar = float(np.mean(tail)) if tail.size else None
    return var, cvar


def var_cvar_irr(irr: np.ndarray, alpha: float = 0.05) -> tuple[float | None, float | None]:
    """VaR-style shortfall vs median at alpha (lower tail); CVaR = mean of tail below p_alpha."""
    v = np.asarray(irr, dtype=np.float64)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return None, None
    q = float(np.percentile(v, alpha * 100))
    med = float(np.percentile(v, 50))
    var = med - q
    tail = v[v <= q]
    cvar = float(np.mean(tail)) if tail.size else None
    return var, cvar


def distribution_summary(x: np.ndarray) -> DistributionSummary:
    return _finite_summary(np.asarray(x, dtype=np.float64))


def build_financial_metrics(
    dscr: np.ndarray,
    irr: np.ndarray,
    covenant_dscr: float,
    *,
    default_threshold_dscr: float = 1.0,
    ebitda: np.ndarray | None = None,
    levered_cf: np.ndarray | None = None,
    nav_proxy_equity: np.ndarray | None = None,
    liquidity_runway_months: np.ndarray | None = None,
    waterfall_dsra_avg_drag: float | None = None,
    structural_pd_from_dscr: bool = False,
) -> FinancialRiskMetrics:
    d = _finite_summary(dscr[np.isfinite(dscr)])
    ir = np.asarray(irr, dtype=np.float64)
    irr_summary = _finite_summary(ir) if np.any(np.isfinite(ir)) else None

    ds = np.asarray(dscr, dtype=np.float64)
    finite_d = ds[np.isfinite(ds)]
    if finite_d.size == 0:
        breach = 0.0
        pod = None
    else:
        breach = float(np.mean(finite_d < covenant_dscr))
        pod = float(np.mean(finite_d < default_threshold_dscr))

    var_irr, cvar_irr = var_cvar_irr(ir)

    e_sum = None
    var_e = cvar_e = None
    if ebitda is not None:
        e = np.asarray(ebitda, dtype=np.float64)
        e_sum = _finite_summary(e)
        var_e, cvar_e = var_cvar_level(e)

    lf_sum = None
    var_lf = cvar_lf = None
    if levered_cf is not None:
        lf = np.asarray(levered_cf, dtype=np.float64)
        lf_sum = _finite_summary(lf)
        var_lf, cvar_lf = var_cvar_level(lf)

    nav_s = None
    var_n = cvar_n = None
    if nav_proxy_equity is not None:
        nv = np.asarray(nav_proxy_equity, dtype=np.float64)
        nav_s = _finite_summary(nv)
        var_n, cvar_n = var_cvar_level(nv)

    lrm = None
    if liquidity_runway_months is not None:
        lr = np.asarray(liquidity_runway_months, dtype=np.float64)
        lr = lr[np.isfinite(lr)]
        if lr.size:
            lrm = _finite_summary(lr)

    merton_pd = structural_equity_pd_proxy(ds) if structural_pd_from_dscr else None

    return FinancialRiskMetrics(
        dscr=d,
        irr_annual=irr_summary,
        covenant_breach_probability=breach,
        probability_of_default_proxy_dscr_lt_1=pod,
        var_irr_95=var_irr,
        cvar_irr_95=cvar_irr,
        ebitda=e_sum,
        var_ebitda_95=var_e,
        cvar_ebitda_95=cvar_e,
        levered_cf=lf_sum,
        var_levered_cf_95=var_lf,
        cvar_levered_cf_95=cvar_lf,
        nav_proxy_equity=nav_s,
        var_nav_proxy_95=var_n,
        cvar_nav_proxy_95=cvar_n,
        liquidity_runway_months=lrm,
        merton_equity_pd_proxy=merton_pd,
        waterfall_dsra_avg_drag=waterfall_dsra_avg_drag,
    )


def build_full_stack_metrics(
    diag: LayerDiagnostics,
    milestone_horizons: list[float] | None = None,
    *,
    full_stack_cfg: FullStackLayerConfig | None = None,
) -> FullStackMetrics:
    if milestone_horizons is None:
        milestone_horizons = [12.0, 15.0, 18.0, 24.0, 30.0]
    mc = milestone_completion_curve(diag.critical_path_completion_months, milestone_horizons)
    p_pue = 0.0
    p_wue = 0.0
    if full_stack_cfg is not None:
        p_pue = float(np.mean(diag.pue_realized > full_stack_cfg.pue_target))
        if full_stack_cfg.wue_target is not None:
            p_wue = float(np.mean(diag.wue_realized > full_stack_cfg.wue_target))
    return FullStackMetrics(
        schedule_delay_months=distribution_summary(diag.schedule_delay_months),
        critical_path_completion_months=distribution_summary(diag.critical_path_completion_months),
        downtime_days=distribution_summary(diag.downtime_days),
        availability=distribution_summary(diag.availability),
        probability_sla_breach=float(np.mean(diag.sla_breach)),
        probability_cyber_material=float(np.mean(diag.cyber_severity)),
        milestone_completion=mc,
        probability_pue_breach=p_pue,
        probability_wue_breach=p_wue,
        grid_gen_joint_stress_days=distribution_summary(diag.joint_stress_days),
    )
