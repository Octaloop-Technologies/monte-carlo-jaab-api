from __future__ import annotations

from collections import defaultdict

import numpy as np

from azraq_mc.macro_definitions import FACTOR_RISK_BUCKET, RiskBucket
from azraq_mc.schemas import FactorAttributionResult


def factor_attribution_dscr_tail_regression(
    z: np.ndarray,
    dscr: np.ndarray,
    factor_names: tuple[str, ...],
    *,
    tail_fraction: float = 0.05,
    min_tail: int = 100,
    levered_cf: np.ndarray | None = None,
) -> FactorAttributionResult:
    """
    OLS on the worst-DSCR tail: DSCR ~ 1 + standardized Z.

    Extended (§4.6): risk-bucket aggregation, pairwise interaction heuristic in tail,
    rough levered-CF loss covariance vs factors for VaR-style decomposition rows.
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
    dim = z_t.shape[1]

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

    bucket_totals: dict[str, float] = defaultdict(float)
    for k, sh in shares.items():
        b: RiskBucket = FACTOR_RISK_BUCKET.get(k, "market_macro")
        bucket_totals[b] += sh

    interaction_top_pair: tuple[str, str] | None = None
    interaction_score: float | None = None
    if dim >= 2:
        best = -1.0
        pair: tuple[str, str] = (factor_names[0], factor_names[1])
        for i in range(dim):
            for j in range(i + 1, dim):
                s = float(np.mean(np.abs(z_t[:, i] * z_t[:, j])))
                if s > best:
                    best = s
                    pair = (factor_names[i], factor_names[j])
        interaction_top_pair = pair
        interaction_score = float(best)

    var_metric_decomposition: dict[str, float] = {}
    if levered_cf is not None:
        cf = np.asarray(levered_cf, dtype=np.float64)
        cf = cf[mask]
        cf_t = cf[order]
        med = float(np.median(cf[np.isfinite(cf)]))
        loss = med - cf_t
        for i, name in enumerate(factor_names):
            if n_tail > 1:
                c = np.cov(z_t[:, i], loss)[0, 1]
                var_metric_decomposition[name] = float(c)
            else:
                var_metric_decomposition[name] = 0.0

    return FactorAttributionResult(
        target="dscr",
        tail_fraction=tail_fraction,
        n_tail_scenarios=n_tail,
        factor_order=factor_names,
        standardized_beta=raw,
        share_of_abs_beta=shares,
        r_squared=float(r2) if r2 is not None else None,
        bucket_shares=dict(bucket_totals),
        interaction_top_pair=interaction_top_pair,
        interaction_score=interaction_score,
        var_metric_decomposition=var_metric_decomposition,
    )
