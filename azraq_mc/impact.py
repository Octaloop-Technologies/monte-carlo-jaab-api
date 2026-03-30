from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from azraq_mc.full_stack_pipeline import LayerDiagnostics, apply_full_stack_layers
from azraq_mc.irr_batch import equity_irr_batch
from azraq_mc.schemas import AssetAssumptions, RiskFactorMargins, ShockArray
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
    layer: LayerDiagnostics | None = None


def _level_debt_service(principal: np.ndarray, rate_annual: np.ndarray, term_years: int) -> np.ndarray:
    """Vectorized fixed-rate, fully amortizing annual payment."""
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


def financial_impact(
    shocks: ShockArray,
    asset: AssetAssumptions,
    margins: RiskFactorMargins | None = None,
) -> FinancialOutcomes:
    """
    Deterministic mapping (Z, assumptions) → outcomes. No sampling inside.

    - 4 macro factors: revenue, capex, opex, rate (always use first 4 columns of Z).
    - With ``asset.full_stack.enabled`` and a 12-factor ShockPack, applies delivery / physical /
      operational / cyber propagation as extra multipliers and downtime effects.
    """
    if margins is None:
        margins = RiskFactorMargins()

    z_full = apply_factor_transforms_z(np.asarray(shocks.z, dtype=np.float64), asset.factor_transforms)
    if z_full.shape[1] < 4:
        raise ValueError("need at least four shock factors")
    if z_full.shape[1] != len(shocks.factor_order):
        raise ValueError("shock width must match factor_order length")

    zm = z_full[:, :4]
    rev_m = np.exp(margins.revenue_log_mean + margins.revenue_log_sigma * zm[:, 0])
    capex_m = np.exp(margins.capex_log_mean + margins.capex_log_sigma * zm[:, 1])
    opex_m = np.exp(margins.opex_log_mean + margins.opex_log_sigma * zm[:, 2])
    rate_shock = margins.rate_shock_sigma * zm[:, 3]
    rev_m, capex_m, opex_m = apply_factor_level_multipliers(rev_m, capex_m, opex_m, asset.factor_transforms)

    layer: LayerDiagnostics | None = None
    if asset.full_stack is not None and asset.full_stack.enabled:
        adj, layer = apply_full_stack_layers(z_full, shocks.factor_order, asset.full_stack)
        rev_m = rev_m * adj.revenue_mult
        capex_m = capex_m * adj.capex_mult
        opex_m = opex_m * adj.opex_mult
        um = adj.utility_price_mult
    else:
        um = np.ones_like(rev_m)

    fin = asset.financing
    capex_total = asset.initial_capex * capex_m
    initial_equity = capex_total * asset.equity_fraction
    debt_principal = capex_total * (1.0 - asset.equity_fraction)

    base_rate = fin.interest_rate_annual
    rate_eff = np.clip(base_rate + rate_shock, 1e-8, 0.5)

    u = asset.utility_opex_annual
    other_opex = asset.base_opex_annual - u
    utility_opex = u * opex_m * um
    ebitda = asset.base_revenue_annual * rev_m - other_opex * opex_m - utility_opex
    debt_service = _level_debt_service(debt_principal, rate_eff, fin.loan_term_years)
    dscr = np.where(debt_service > 1e-9, ebitda / debt_service, np.inf)

    floor = asset.factor_transforms.mitigation_dscr_floor if asset.factor_transforms else None
    dscr = apply_mitigation_dscr_floor(dscr, floor)

    irr = equity_irr_batch(initial_equity, (ebitda - debt_service) * (1.0 - asset.tax_rate), asset.horizon_years)

    return FinancialOutcomes(
        dscr=dscr,
        irr=irr,
        ebitda=ebitda,
        debt_service=debt_service,
        revenue_multiplier=rev_m,
        initial_equity=initial_equity,
        utility_opex=utility_opex,
        layer=layer,
    )
