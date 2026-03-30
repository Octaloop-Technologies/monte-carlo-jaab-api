from __future__ import annotations

import numpy as np

from azraq_mc.schemas import FactorAttributionResult


def factor_attribution_dscr_tail_regression(
    z: np.ndarray,
    dscr: np.ndarray,
    factor_names: tuple[str, ...],
    *,
    tail_fraction: float = 0.05,
    min_tail: int = 100,
) -> FactorAttributionResult:
    """
    OLS on the worst-DSCR tail: DSCR ~ 1 + standardized Z.

    Shares use absolute beta coefficients normalised to sum 1 (interpret as rough relative influence).
    """
    z = np.asarray(z, dtype=np.float64)
    y = np.asarray(dscr, dtype=np.float64)
    mask = np.isfinite(y)
    z, y = z[mask], y[mask]
    n = y.size
    if z.shape[1] != len(factor_names):
        raise ValueError("factor_names length must match Z columns")

    thr_idx = max(int(np.floor(tail_fraction * n)), min(min_tail, n))
    thr_idx = min(thr_idx, n)
    order = np.argsort(y)[: max(thr_idx, 1)]
    z_t, y_t = z[order], y[order]
    n_tail = z_t.shape[0]

    z_s = (z_t - z_t.mean(axis=0)) / np.where(z_t.std(axis=0) < 1e-12, 1.0, z_t.std(axis=0))
    x = np.column_stack([np.ones(n_tail), z_s])
    beta, *_ = np.linalg.lstsq(x, y_t, rcond=None)
    resid = y_t - x @ beta
    ss_res = float(np.sum(resid**2))
    ss_tot = float(np.sum((y_t - float(np.mean(y_t))) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else None

    raw = {factor_names[i]: float(beta[i + 1]) for i in range(len(factor_names))}
    abs_sum = sum(abs(v) for v in raw.values()) or 1.0
    shares = {k: abs(v) / abs_sum for k, v in raw.items()}

    return FactorAttributionResult(
        target="dscr",
        tail_fraction=tail_fraction,
        n_tail_scenarios=n_tail,
        factor_order=factor_names,
        standardized_beta=raw,
        share_of_abs_beta=shares,
        r_squared=float(r2) if r2 is not None else None,
    )
