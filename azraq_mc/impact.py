from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from azraq_mc.cashflow_waterfall import (
    dsra_annual_funding_proxy,
    lc_annual_fee,
    liquidity_buffer_for_asset,
    liquidity_runway_months,
    sculpted_debt_service_per_period,
    weighted_tranche_coupon_add,
)
from azraq_mc.full_stack_pipeline import LayerDiagnostics, apply_full_stack_layers
from azraq_mc.irr_batch import equity_irr_batch
from azraq_mc.macro_curves import rate_additive_shock, tenor_shock_means_report
from azraq_mc.schemas import AssetAssumptions, RiskFactorMargins, ShockArray, ShockPackSpec
from azraq_mc.transforms import (
    apply_factor_level_multipliers,
    apply_factor_transforms_z,
    apply_mitigation_dscr_floor,
)


@dataclass
class FinancialOutcomes:
    dscr: np.ndarray
    irr: np.ndarray
    ebitda: np.ndarray
    debt_service: np.ndarray
    revenue_multiplier: np.ndarray
    initial_equity: np.ndarray
    utility_opex: np.ndarray
    levered_cf: np.ndarray
    nav_proxy_equity: np.ndarray
    layer: LayerDiagnostics | None = None
    extensions: dict[str, Any] | None = None
    liquidity_runway_months: np.ndarray | None = None


def _level_debt_service(principal: np.ndarray, rate_annual: np.ndarray, term_years: int) -> np.ndarray:
    p = np.asarray(principal, dtype=np.float64)
    r = np.maximum(np.asarray(rate_annual, dtype=np.float64), 1e-8)
    n = float(term_years)
    mask = p <= 0
    pay = np.zeros_like(p, dtype=np.float64)
    ok = ~mask
    if np.any(ok):
        po = p[ok]
        ro = r[ok]
        pay[ok] = po * ro / (1.0 - (1.0 + ro) ** (-n))
    return pay


def _rate_col(factor_order: tuple[str, ...], shock_spec: ShockPackSpec | None) -> int:
    key = "rate"
    if shock_spec and shock_spec.macro_term_structure:
        key = shock_spec.macro_term_structure.rate_factor_key
    try:
        return list(factor_order).index(key)
    except ValueError:
        return min(3, len(factor_order) - 1)


def _apply_inflation(
    z_slice: np.ndarray,
    factor_order: tuple[str, ...],
    shock_spec: ShockPackSpec | None,
    rev_m: np.ndarray,
    capex_m: np.ndarray,
    opex_m: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    inf = shock_spec.inflation_process if shock_spec else None
    if inf is None or not inf.enabled:
        return rev_m, capex_m, opex_m
    try:
        ic = list(factor_order).index(inf.z_factor_key)
    except ValueError:
        ic = 2
    zi = z_slice[:, ic]
    infl = np.exp(inf.log_sigma * zi)
    return (
        rev_m * (infl**inf.revenue_beta),
        capex_m * (infl**inf.capex_beta),
        opex_m * (infl**inf.opex_beta),
    )


def _dscr_denom(
    debt_service: np.ndarray,
    dsra: np.ndarray,
    lc: np.ndarray,
    wf_enabled: bool,
) -> np.ndarray:
    if wf_enabled:
        return np.maximum(debt_service + dsra + lc, 1e-9)
    return np.maximum(debt_service, 1e-9)


def financial_impact(
    shocks: ShockArray,
    asset: AssetAssumptions,
    margins: RiskFactorMargins | None = None,
    *,
    shock_spec: ShockPackSpec | None = None,
) -> FinancialOutcomes:
    """
    Deterministic (Z, assumptions) → outcomes. Randomness only in Z upstream.

    - 2d Z: classic single-stage model.
    - 3d Z: per-period macro shocks; DSCR = min over time; EBITDA reported as mean path;
      capital structure locked from t=0 slice (unless waterfall sculpting adjusts service path).
    """
    if margins is None:
        margins = RiskFactorMargins()

    z_full = apply_factor_transforms_z(np.asarray(shocks.z, dtype=np.float64), asset.factor_transforms)
    if z_full.shape[1] < 4:
        raise ValueError("need at least four shock factors")
    if z_full.shape[1] != len(shocks.factor_order):
        raise ValueError("shock width must match factor_order length")

    if z_full.ndim == 2:
        return _financial_impact_2d(z_full, shocks.factor_order, asset, margins, shock_spec)
    if z_full.ndim == 3:
        return _financial_impact_path(z_full, shocks.factor_order, asset, margins, shock_spec)
    raise ValueError("z must be 2d or 3d")


def _financial_impact_2d(
    z_full: np.ndarray,
    factor_order: tuple[str, ...],
    asset: AssetAssumptions,
    margins: RiskFactorMargins,
    shock_spec: ShockPackSpec | None,
) -> FinancialOutcomes:
    fin = asset.financing
    wf = asset.waterfall
    wf_on = wf is not None and wf.enabled
    zm = z_full[:, :4]
    rev_m = np.exp(margins.revenue_log_mean + margins.revenue_log_sigma * zm[:, 0])
    capex_m = np.exp(margins.capex_log_mean + margins.capex_log_sigma * zm[:, 1])
    opex_m = np.exp(margins.opex_log_mean + margins.opex_log_sigma * zm[:, 2])
    rc = _rate_col(factor_order, shock_spec)
    rate_shock = rate_additive_shock(z_full[:, rc], margins, shock_spec.macro_term_structure if shock_spec else None)
    rev_m, capex_m, opex_m = apply_factor_level_multipliers(rev_m, capex_m, opex_m, asset.factor_transforms)

    layer: LayerDiagnostics | None = None
    if asset.full_stack is not None and asset.full_stack.enabled:
        adj, layer = apply_full_stack_layers(z_full, factor_order, asset.full_stack)
        rev_m = rev_m * adj.revenue_mult
        capex_m = capex_m * adj.capex_mult
        opex_m = opex_m * adj.opex_mult
        um = adj.utility_price_mult
    else:
        um = np.ones_like(rev_m)

    rev_m, capex_m, opex_m = _apply_inflation(z_full, factor_order, shock_spec, rev_m, capex_m, opex_m)

    capex_total = asset.initial_capex * capex_m
    initial_equity = capex_total * asset.equity_fraction
    debt_principal = capex_total * (1.0 - asset.equity_fraction)
    spread = weighted_tranche_coupon_add(wf) if wf_on else 0.0
    rate_eff = np.clip(fin.interest_rate_annual + rate_shock + spread, 1e-8, 0.5)

    u = asset.utility_opex_annual
    other_opex = asset.base_opex_annual - u
    utility_opex = u * opex_m * um
    ebitda = asset.base_revenue_annual * rev_m - other_opex * opex_m - utility_opex
    debt_service = _level_debt_service(debt_principal, rate_eff, fin.loan_term_years)
    dsra = dsra_annual_funding_proxy(debt_service, wf) if wf_on else np.zeros_like(debt_service)
    lc = lc_annual_fee(debt_principal, wf) if wf_on else np.zeros_like(debt_principal)
    denom = _dscr_denom(debt_service, dsra, lc, wf_on)
    dscr = ebitda / denom
    floor_mt = asset.factor_transforms.mitigation_dscr_floor if asset.factor_transforms else None
    dscr = apply_mitigation_dscr_floor(dscr, floor_mt)

    levered_cf = (ebitda - debt_service - dsra - lc) * (1.0 - asset.tax_rate)
    irr = equity_irr_batch(initial_equity, levered_cf, asset.horizon_years)
    nav_proxy = initial_equity + asset.horizon_years * levered_cf

    runway = None
    if asset.liquidity is not None and asset.liquidity.enabled:
        buf = np.full_like(ebitda, liquidity_buffer_for_asset(asset))
        runway = liquidity_runway_months(ebitda, debt_service, dsra, lc, asset.tax_rate, buf)

    ext: dict[str, Any] = {}
    if shock_spec and shock_spec.macro_term_structure:
        ext["macro_tenor_additive_mean_decimal"] = tenor_shock_means_report(
            z_full[:, rc], margins, shock_spec.macro_term_structure
        )
    if wf_on:
        ext["waterfall_dsra_mean_annual"] = float(np.mean(dsra))
        ext["waterfall_lc_mean_annual"] = float(np.mean(lc))

    return FinancialOutcomes(
        dscr=dscr,
        irr=irr,
        ebitda=ebitda,
        debt_service=debt_service,
        revenue_multiplier=rev_m,
        initial_equity=initial_equity,
        utility_opex=utility_opex,
        levered_cf=levered_cf,
        nav_proxy_equity=nav_proxy,
        layer=layer,
        extensions=ext or None,
        liquidity_runway_months=runway,
    )


def _financial_impact_path(
    z_full: np.ndarray,
    factor_order: tuple[str, ...],
    asset: AssetAssumptions,
    margins: RiskFactorMargins,
    shock_spec: ShockPackSpec | None,
) -> FinancialOutcomes:
    fin = asset.financing
    wf = asset.waterfall
    wf_on = wf is not None and wf.enabled
    n, n_f, t_max = z_full.shape
    if n_f < 4:
        raise ValueError("need at least four factors")

    zm0 = z_full[:, :4, 0]
    rev0 = np.exp(margins.revenue_log_mean + margins.revenue_log_sigma * zm0[:, 0])
    capex_m0 = np.exp(margins.capex_log_mean + margins.capex_log_sigma * zm0[:, 1])
    opex_m0 = np.exp(margins.opex_log_mean + margins.opex_log_sigma * zm0[:, 2])
    rc = _rate_col(factor_order, shock_spec)
    rate_shock0 = rate_additive_shock(z_full[:, rc, 0], margins, shock_spec.macro_term_structure if shock_spec else None)
    rev0, capex_m0, opex_m0 = apply_factor_level_multipliers(rev0, capex_m0, opex_m0, asset.factor_transforms)

    fs = asset.full_stack
    layer: LayerDiagnostics | None = None
    if fs is not None and fs.enabled:
        z0 = z_full[:, :, 0]
        adj0, _ = apply_full_stack_layers(z0, factor_order, fs)
        capex_m0 = capex_m0 * adj0.capex_mult

    rev0, capex_m0, opex_m0 = _apply_inflation(z_full[:, :, 0], factor_order, shock_spec, rev0, capex_m0, opex_m0)

    capex_total = asset.initial_capex * capex_m0
    initial_equity = capex_total * asset.equity_fraction
    debt_principal = capex_total * (1.0 - asset.equity_fraction)
    spread = weighted_tranche_coupon_add(wf) if wf_on else 0.0
    rate_eff = np.clip(fin.interest_rate_annual + rate_shock0 + spread, 1e-8, 0.5)
    debt_service_base = _level_debt_service(debt_principal, rate_eff, fin.loan_term_years)
    lc = lc_annual_fee(debt_principal, wf) if wf_on else np.zeros_like(debt_principal)

    u = asset.utility_opex_annual
    other_opex = asset.base_opex_annual - u
    ebitda_acc = np.zeros(n, dtype=np.float64)
    dscr_min = np.full(n, np.inf, dtype=np.float64)
    rev_rep = np.ones(n, dtype=np.float64)
    lev_cf_acc = np.zeros(n, dtype=np.float64)
    dsra_acc = np.zeros(n, dtype=np.float64)
    ds_paid_acc = np.zeros(n, dtype=np.float64)

    sculpt = wf_on and wf is not None and wf.sculpt_target_dscr is not None

    for t in range(t_max):
        zt = z_full[:, :, t]
        zm = zt[:, :4]
        rev_m = np.exp(margins.revenue_log_mean + margins.revenue_log_sigma * zm[:, 0])
        opex_m = np.exp(margins.opex_log_mean + margins.opex_log_sigma * zm[:, 2])
        rev_m, _, opex_m = apply_factor_level_multipliers(rev_m, np.ones_like(rev_m), opex_m, asset.factor_transforms)
        rev_m, _, opex_m = _apply_inflation(zt, factor_order, shock_spec, rev_m, np.ones_like(rev_m), opex_m)
        um = np.ones_like(rev_m)
        if fs is not None and fs.enabled:
            adj, lay = apply_full_stack_layers(zt, factor_order, fs)
            rev_m = rev_m * adj.revenue_mult
            opex_m = opex_m * adj.opex_mult
            um = adj.utility_price_mult
            if t == t_max - 1:
                layer = lay
        utility_opex = u * opex_m * um
        ebitda_t = asset.base_revenue_annual * rev_m - other_opex * opex_m - utility_opex
        ebitda_acc += ebitda_t

        ds_t = (
            sculpted_debt_service_per_period(ebitda_t, debt_service_base, float(wf.sculpt_target_dscr))
            if sculpt and wf is not None
            else debt_service_base
        )
        dsra_t = dsra_annual_funding_proxy(ds_t, wf) if wf_on else np.zeros_like(ds_t)
        denom = _dscr_denom(ds_t, dsra_t, lc, wf_on)
        dscr_t = ebitda_t / denom
        dscr_min = np.minimum(dscr_min, dscr_t)
        dsra_acc += dsra_t
        ds_paid_acc += ds_t
        lev_cf_acc += (ebitda_t - ds_t - dsra_t - lc) * (1.0 - asset.tax_rate)
        if t == t_max - 1:
            rev_rep = rev_m

    ebitda_mean = ebitda_acc / float(t_max)
    dscr = dscr_min
    dscr = apply_mitigation_dscr_floor(dscr, asset.factor_transforms.mitigation_dscr_floor if asset.factor_transforms else None)

    mean_dsra = dsra_acc / float(t_max)
    mean_ds = ds_paid_acc / float(t_max)
    levered_cf = lev_cf_acc / float(t_max)
    irr = equity_irr_batch(initial_equity, levered_cf, asset.horizon_years)
    nav_proxy = initial_equity + asset.horizon_years * levered_cf

    runway = None
    if asset.liquidity is not None and asset.liquidity.enabled:
        buf = np.full(n, liquidity_buffer_for_asset(asset))
        runway = liquidity_runway_months(ebitda_mean, mean_ds, mean_dsra, lc, asset.tax_rate, buf)

    ext: dict[str, Any] = {"path_mean_debt_service": float(np.mean(mean_ds))}
    if shock_spec and shock_spec.macro_term_structure:
        ext["macro_tenor_additive_mean_decimal"] = tenor_shock_means_report(
            z_full[:, rc, -1], margins, shock_spec.macro_term_structure
        )
    if wf_on:
        ext["waterfall_dsra_mean_annual"] = float(np.mean(mean_dsra))

    return FinancialOutcomes(
        dscr=dscr,
        irr=irr,
        ebitda=ebitda_mean,
        debt_service=debt_service_base,
        revenue_multiplier=rev_rep,
        initial_equity=initial_equity,
        utility_opex=np.zeros(n),
        levered_cf=levered_cf,
        nav_proxy_equity=nav_proxy,
        layer=layer,
        extensions=ext,
        liquidity_runway_months=runway,
    )
