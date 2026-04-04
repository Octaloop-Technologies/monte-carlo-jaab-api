"""§4.6 — Euler-style and Shapley-style (incremental R²) risk contributions on a loss metric."""
from __future__ import annotations

import numpy as np


def _ols_r2(x: np.ndarray, y: np.ndarray) -> float:
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64).reshape(-1)
    if x.size == 0 or y.size == 0:
        return 0.0
    if x.ndim == 1:
        x = x[:, None]
    n, k = x.shape
    if n < k + 2:
        return 0.0
    xm = np.column_stack([np.ones(n), x])
    beta, *_ = np.linalg.lstsq(xm, y, rcond=None)
    pred = xm @ beta
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - float(np.mean(y))) ** 2))
    if ss_tot <= 0:
        return 0.0
    return max(0.0, 1.0 - ss_res / ss_tot)


def euler_covariance_shares(z: np.ndarray, loss: np.ndarray, factor_names: tuple[str, ...]) -> dict[str, float]:
    """Normalised covariance(loss, z_j); global linear marginal view."""
    z = np.asarray(z, dtype=np.float64)
    l = np.asarray(loss, dtype=np.float64).reshape(-1)
    n = z.shape[0]
    if z.shape[1] != len(factor_names):
        raise ValueError("factor_names must match Z width")
    mask = np.isfinite(l) & np.all(np.isfinite(z), axis=1)
    z, l = z[mask], l[mask]
    if z.shape[0] < 5:
        return {k: 1.0 / len(factor_names) for k in factor_names}
    zc = z - z.mean(axis=0, keepdims=True)
    lc = l - l.mean()
    covs = np.array([float(np.dot(zc[:, j], lc) / zc.shape[0]) for j in range(zc.shape[1])])
    a = np.abs(covs)
    s = float(a.sum()) or 1.0
    return {factor_names[j]: float(a[j] / s) for j in range(len(factor_names))}


def shapley_incremental_r2(
    z: np.ndarray,
    loss: np.ndarray,
    factor_names: tuple[str, ...],
    *,
    n_perm: int = 40,
    seed: int = 42,
) -> dict[str, float]:
    """Permutation sampling of incremental OLS R² when factors enter in random order."""
    z = np.asarray(z, dtype=np.float64)
    l = np.asarray(loss, dtype=np.float64).reshape(-1)
    mask = np.isfinite(l) & np.all(np.isfinite(z), axis=1)
    z, l = z[mask], l[mask]
    n, k = z.shape
    if k != len(factor_names):
        raise ValueError("factor_names must match Z width")
    if n < k + 3:
        return {factor_names[i]: 1.0 / k for i in range(k)}
    rng = np.random.default_rng(seed)
    contrib = np.zeros(k, dtype=np.float64)
    for _ in range(n_perm):
        order = rng.permutation(k)
        prev = 0.0
        included: list[int] = []
        for j in order:
            included.append(j)
            cols = z[:, np.array(sorted(included), dtype=int)]
            r2 = _ols_r2(cols, l)
            contrib[j] += max(0.0, r2 - prev)
            prev = r2
    contrib /= float(n_perm)
    s = float(np.sum(np.abs(contrib))) or 1.0
    return {factor_names[i]: float(abs(contrib[i]) / s) for i in range(k)}


def downside_loss_from_cf(levered_cf: np.ndarray) -> np.ndarray:
    """Loss = max(0, median(CF) - CF)."""
    cf = np.asarray(levered_cf, dtype=np.float64)
    med = float(np.median(cf[np.isfinite(cf)]))
    return np.maximum(0.0, med - cf)
