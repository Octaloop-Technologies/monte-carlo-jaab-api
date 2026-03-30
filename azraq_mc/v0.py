from __future__ import annotations

import uuid
from datetime import datetime, timezone

import numpy as np
import numpy_financial as npf

from azraq_mc.impact import financial_impact
from azraq_mc.schemas import (
    AssetAssumptions,
    BaseCaseMetrics,
    BaseCaseResult,
    RiskFactorMargins,
    ShockArray,
    SimulationRunMetadata,
)
from azraq_mc.versioning import layer_versions_bundle


def _equity_npv(initial_equity: float, annual_cf: float, years: int, rate: float) -> float:
    if initial_equity <= 0:
        return float("nan")
    cfs = np.empty(years + 1, dtype=np.float64)
    cfs[0] = -initial_equity
    cfs[1:] = annual_cf
    return float(npf.npv(rate, cfs))


def run_v0_base_case(
    asset: AssetAssumptions,
    *,
    margins: RiskFactorMargins | None = None,
    model_version: str = "azraq-mc-v0",
    run_id: str | None = None,
    user_id: str | None = None,
) -> BaseCaseResult:
    """V0: deterministic zero-shock path (z = 0)."""
    if margins is None:
        margins = RiskFactorMargins()
    z0 = np.zeros((1, 4), dtype=np.float64)
    shocks = ShockArray(
        shockpack_id="v0-deterministic",
        seed=0,
        n_scenarios=1,
        factor_order=("revenue", "capex", "opex", "rate"),
        z=z0,
    )
    out = financial_impact(shocks, asset, margins=margins)
    d0 = float(out.dscr[0])
    irr0 = float(out.irr[0]) if np.isfinite(out.irr[0]) else None
    e0 = float(out.ebitda[0])
    ds0 = float(out.debt_service[0])
    eq0 = float(out.initial_equity[0])
    rate_base = asset.financing.interest_rate_annual
    rate_eff = float(np.clip(rate_base, 1e-8, 0.5))

    rev_m = float(out.revenue_multiplier[0])
    capex_m = float(np.exp(margins.capex_log_mean + margins.capex_log_sigma * z0[0, 1]))
    opex_m = float(np.exp(margins.opex_log_mean + margins.opex_log_sigma * z0[0, 2]))
    annual_rev = float(asset.base_revenue_annual * rev_m)
    utility_exp = float(out.utility_opex[0])

    npv = None
    if asset.equity_discount_rate_for_npv is not None:
        cf1 = (e0 - ds0) * (1.0 - asset.tax_rate)
        npv = _equity_npv(eq0, cf1, asset.horizon_years, asset.equity_discount_rate_for_npv)

    ev = None
    if asset.project_discount_rate_for_ev is not None:
        capex0 = float(asset.initial_capex * capex_m)
        fcf_u = e0 * (1.0 - asset.tax_rate)
        cfs = np.empty(asset.horizon_years + 1, dtype=np.float64)
        cfs[0] = -capex0
        cfs[1:] = fcf_u
        ev = float(npf.npv(asset.project_discount_rate_for_ev, cfs))

    base = BaseCaseMetrics(
        dscr=d0,
        irr_annual=irr0,
        annual_revenue=annual_rev,
        ebitda=e0,
        debt_service=ds0,
        initial_equity=eq0,
        utility_opex_exposure=utility_exp,
        revenue_multiplier=rev_m,
        capex_multiplier=capex_m,
        opex_multiplier=opex_m,
        effective_interest_rate=rate_eff,
        npv_equity=npv,
        enterprise_value=ev,
    )
    meta = SimulationRunMetadata(
        run_id=run_id or str(uuid.uuid4()),
        shockpack_id="v0-deterministic",
        assumption_set_id=asset.assumption_set_id,
        asset_id=asset.asset_id,
        model_version=model_version,
        seed=0,
        n_scenarios=1,
        sampling_method="monte_carlo",
        created_at_utc=datetime.now(timezone.utc),
        execution_mode="v0_base",
        user_id=user_id,
        layer_versions=layer_versions_bundle(),
    )
    return BaseCaseResult(metadata=meta, base=base)
