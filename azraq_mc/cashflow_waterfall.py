"""Multi-tranche, DSRA / LC stylised charges, sculpting, liquidity runway helpers (§3.2 / §4.5)."""
from __future__ import annotations

import numpy as np

from azraq_mc.schemas import AssetAssumptions, WaterfallAssumptions


def weighted_tranche_coupon_add(wf: WaterfallAssumptions) -> float:
    if not wf.enabled or not wf.tranches:
        return 0.0
    return float(sum(t.share_of_debt * t.coupon_spread_add for t in wf.tranches))


def level_debt_service_path(
    principal: np.ndarray,
    rate_annual: np.ndarray,
    term_years: int,
) -> np.ndarray:
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


def sculpted_debt_service_per_period(
    ebitda_t: np.ndarray,
    debt_service_static: np.ndarray,
    sculpt_dscr: float,
) -> np.ndarray:
    """Cap cash debt service when EBITDA supports less while targeting a DSCR floor style path."""
    eb = np.asarray(ebitda_t, dtype=np.float64)
    ds0 = np.asarray(debt_service_static, dtype=np.float64)
    cap = np.maximum(eb / sculpt_dscr, 1e-9)
    return np.minimum(ds0, cap)


def dsra_annual_funding_proxy(debt_service: np.ndarray, wf: WaterfallAssumptions) -> np.ndarray:
    """Build-a-reserve charge as fraction of debt service until target months funded (linear proxy)."""
    ds = np.asarray(debt_service, dtype=np.float64)
    if not wf.enabled or wf.dsra_months_of_debt_service <= 0:
        return np.zeros_like(ds)
    target_frac = min(1.0, wf.dsra_months_of_debt_service / 12.0)
    return ds * target_frac * wf.dsra_funding_speed


def lc_annual_fee(debt_principal: np.ndarray, wf: WaterfallAssumptions) -> np.ndarray:
    if not wf.enabled:
        return np.zeros_like(debt_principal, dtype=np.float64)
    return np.asarray(debt_principal, dtype=np.float64) * wf.lc_commitment_fee_annual_pct


def liquidity_runway_months(
    ebitda_series: np.ndarray,
    debt_service_series: np.ndarray,
    dsra_charge: np.ndarray,
    lc_fee: np.ndarray,
    tax_rate: float,
    liquidity_buffer_annual: np.ndarray,
) -> np.ndarray:
    """
    Months of buffer / mean positive after-tax cash shortfall ( stylised LMT proxy ).
    ebitda_series: (n, t) or (n,) broadcast
    """
    eb = np.asarray(ebitda_series, dtype=np.float64)
    ds = np.asarray(debt_service_series, dtype=np.float64)
    dr = np.asarray(dsra_charge, dtype=np.float64)
    lc = np.asarray(lc_fee, dtype=np.float64)
    buf = np.asarray(liquidity_buffer_annual, dtype=np.float64)
    if eb.ndim == 1:
        cf = (eb - ds - dr - lc) * (1.0 - tax_rate)
        short = np.maximum(0.0, -cf)
        denom = np.maximum(short / 12.0, 1e-6)
        return buf / denom
    # (n, t)
    cf = (eb - ds - dr - lc) * (1.0 - tax_rate)
    short = np.maximum(0.0, -cf)
    mean_monthly_short = np.mean(short, axis=1) / 12.0
    denom = np.maximum(mean_monthly_short, 1e-6)
    return buf / denom


def structural_equity_pd_proxy(dscr: np.ndarray, asset_vol_mult: float = 1.0) -> float:
    """Logistic map from distance-to-default using DSCR moments (no external calibrators)."""
    d = np.asarray(dscr, dtype=np.float64)
    d = d[np.isfinite(d)]
    if d.size == 0:
        return 0.0
    med = float(np.percentile(d, 50))
    iqr = float(np.percentile(d, 75) - np.percentile(d, 25))
    sig = max(iqr / 1.349, 1e-4) * asset_vol_mult
    dd = (med - 1.0) / sig
    return float(1.0 / (1.0 + np.exp(dd * 1.5)))


def liquidity_buffer_for_asset(asset: AssetAssumptions) -> float:
    liq = asset.liquidity
    if liq is None or not liq.enabled:
        return 0.0
    base = liq.cash_buffer_fixed + liq.minimum_cash_months_opex * (asset.base_opex_annual / 12.0)
    return float(base)
