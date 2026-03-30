from __future__ import annotations

import numpy as np

from azraq_mc.full_stack_pipeline import LayerDiagnostics, milestone_completion_curve
from azraq_mc.schemas import DistributionSummary, FinancialRiskMetrics, FullStackMetrics


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

    return FinancialRiskMetrics(
        dscr=d,
        irr_annual=irr_summary,
        covenant_breach_probability=breach,
        probability_of_default_proxy_dscr_lt_1=pod,
        var_irr_95=var_irr,
        cvar_irr_95=cvar_irr,
    )


def build_full_stack_metrics(diag: LayerDiagnostics, milestone_horizons: list[float] | None = None) -> FullStackMetrics:
    if milestone_horizons is None:
        milestone_horizons = [12.0, 15.0, 18.0, 24.0, 30.0]
    mc = milestone_completion_curve(diag.critical_path_completion_months, milestone_horizons)
    return FullStackMetrics(
        schedule_delay_months=distribution_summary(diag.schedule_delay_months),
        critical_path_completion_months=distribution_summary(diag.critical_path_completion_months),
        downtime_days=distribution_summary(diag.downtime_days),
        availability=distribution_summary(diag.availability),
        probability_sla_breach=float(np.mean(diag.sla_breach)),
        probability_cyber_material=float(np.mean(diag.cyber_severity)),
        milestone_completion=mc,
    )
