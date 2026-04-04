"""§3.1.1 — Lightweight benchmark / term-structure aggregation for rate shocks (not a full curve engine)."""
from __future__ import annotations

import numpy as np

from azraq_mc.schemas import MacroTermStructureSpec, RiskFactorMargins


def macro_effective_vol_scalar(spec: MacroTermStructureSpec) -> float:
    """
    Scalar that multiplies `margins.rate_shock_sigma * z_rate` so parallel shifts load across tenors.
    """
    n = len(spec.tenor_years)
    if spec.loadings is None or len(spec.loadings) == 0:
        load = np.ones(n, dtype=np.float64) / n
    else:
        load = np.asarray(spec.loadings, dtype=np.float64)
        if load.shape[0] != n:
            raise ValueError("macro_term_structure.loadings must match tenor_years length")
        s = float(load.sum())
        load = load / (s if s > 0 else 1.0)
    if spec.parallel_vol_multipliers is None:
        vols = np.ones(n, dtype=np.float64)
    else:
        vols = np.asarray(spec.parallel_vol_multipliers, dtype=np.float64)
        if vols.shape[0] != n:
            raise ValueError("parallel_vol_multipliers length must match tenors")
    return float(np.dot(load, vols))


def rate_additive_shock(
    z_rate: np.ndarray,
    margins: RiskFactorMargins,
    macro: MacroTermStructureSpec | None,
) -> np.ndarray:
    zr = np.asarray(z_rate, dtype=np.float64)
    scale = macro_effective_vol_scalar(macro) if macro is not None else 1.0
    return margins.rate_shock_sigma * zr * scale


def tenor_shock_means_report(
    z_rate: np.ndarray,
    margins: RiskFactorMargins,
    spec: MacroTermStructureSpec,
) -> dict[str, float]:
    """Per-tenor mean additive shock (decimal) using loadings × vol (diagnostic, not a curve sim)."""
    zr = np.asarray(z_rate, dtype=np.float64).reshape(-1)
    m = float(np.mean(zr)) if zr.size else 0.0
    n = len(spec.tenor_years)
    if spec.loadings is None:
        load = np.ones(n, dtype=np.float64) / n
    else:
        load = np.asarray(spec.loadings, dtype=np.float64)
        load = load / max(float(load.sum()), 1e-9)
    if spec.parallel_vol_multipliers is not None:
        vols = np.asarray(spec.parallel_vol_multipliers, dtype=np.float64)
    else:
        vols = np.ones(n, dtype=np.float64)
    out: dict[str, float] = {}
    for i, y in enumerate(spec.tenor_years):
        key = f"{y:.4g}y"
        out[key] = margins.rate_shock_sigma * m * float(load[i]) * float(vols[i])
    return out
