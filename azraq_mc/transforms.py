from __future__ import annotations

import numpy as np

from azraq_mc.schemas import AssetFactorTransforms


def apply_factor_transforms_z(z: np.ndarray, t: AssetFactorTransforms | None) -> np.ndarray:
    """Scale shock indices before marginal/lognormal mapping (Layer 2, vectorised)."""
    if t is None:
        return z
    z = np.asarray(z, dtype=np.float64).copy()
    z[:, 0] *= t.revenue_shock_scale
    z[:, 1] *= t.capex_shock_scale
    z[:, 2] *= t.opex_shock_scale
    z[:, 3] *= t.rate_shock_scale
    return z


def apply_factor_level_multipliers(
    rev_m: np.ndarray,
    capex_m: np.ndarray,
    opex_m: np.ndarray,
    t: AssetFactorTransforms | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Regional / design level shifts on effective multipliers after shocks."""
    if t is None:
        return rev_m, capex_m, opex_m
    return (
        rev_m * t.revenue_level_multiplier,
        capex_m * t.capex_level_multiplier,
        opex_m * t.opex_level_multiplier,
    )


def apply_mitigation_dscr_floor(dscr: np.ndarray, floor: float | None) -> np.ndarray:
    """Contractual DSCR floor (mitigation) applied deterministically post-calculation."""
    if floor is None or floor <= 0:
        return dscr
    d = np.asarray(dscr, dtype=np.float64)
    out = d.copy()
    fin = np.isfinite(out)
    out[fin] = np.maximum(out[fin], floor)
    return out
