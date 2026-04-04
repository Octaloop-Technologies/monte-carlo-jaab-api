from __future__ import annotations

import numpy as np
from scipy.stats import qmc, norm

from azraq_mc.schemas import ShockArray, ShockPackSpec


def _validate_correlation(corr: np.ndarray) -> np.ndarray:
    c = np.asarray(corr, dtype=np.float64)
    if c.ndim != 2 or c.shape[0] != c.shape[1]:
        raise ValueError("correlation must be a square matrix")
    if not np.allclose(c, c.T):
        raise ValueError("correlation must be symmetric")
    eig = np.linalg.eigvalsh(c)
    if np.min(eig) < -1e-8:
        raise ValueError("correlation must be positive semidefinite")
    return c


def generate_standard_normals(
    n: int,
    dim: int,
    seed: int,
    method: str,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    if method == "monte_carlo":
        return rng.standard_normal(size=(n, dim))
    if method == "latin_hypercube":
        sampler = qmc.LatinHypercube(d=dim, seed=seed)
        u = sampler.random(n=n)
        z = norm.ppf(np.clip(u, 1e-12, 1 - 1e-12))
        return z.astype(np.float64)
    if method == "sobol":
        eng = qmc.Sobol(d=dim, scramble=True, seed=seed)
        m = int(np.ceil(np.log2(max(n, 1))))
        cap = 2**m
        u = eng.random(cap)[:n]
        z = norm.ppf(np.clip(u, 1e-12, 1 - 1e-12))
        return z.astype(np.float64)
    raise ValueError(f"unknown sampling method: {method}")


def apply_copula(z_corr: np.ndarray, spec: ShockPackSpec) -> np.ndarray:
    """Gaussian copula (identity) vs Student-t style radial scaling for heavier joint tails."""
    if spec.copula == "gaussian":
        return z_corr
    if spec.copula == "student_t":
        rng = np.random.default_rng(int(spec.seed) + 1_000_003)
        w = rng.chisquare(df=spec.t_degrees_freedom, size=z_corr.shape[0]) / spec.t_degrees_freedom
        w = np.maximum(w, 1e-12)
        return z_corr / np.sqrt(w[:, None])
    raise ValueError(f"unknown copula {spec.copula}")


def generate_correlated_z(spec: ShockPackSpec) -> np.ndarray:
    """Independent normals → correlated Z (Cholesky) → optional copula."""
    corr = _validate_correlation(np.asarray(spec.correlation, dtype=np.float64))
    l = np.linalg.cholesky(corr)
    z0 = generate_standard_normals(spec.n_scenarios, corr.shape[0], spec.seed, spec.sampling_method)
    z_corr = z0 @ l.T
    return apply_copula(z_corr, spec)


def generate_correlated_z_paths(spec: ShockPackSpec) -> np.ndarray:
    """
    Shape (n_scenarios, n_factors) when time_grid absent or n_periods==1;
    else (n_scenarios, n_factors, n_periods) with iid or AR(1) temporal dynamics.
    """
    tg = spec.time_grid
    if tg is None or tg.n_periods <= 1:
        return generate_correlated_z(spec)

    corr = _validate_correlation(np.asarray(spec.correlation, dtype=np.float64))
    l = np.linalg.cholesky(corr)
    n, dim, t_max = spec.n_scenarios, corr.shape[0], tg.n_periods

    def step_innov(seed_off: int) -> np.ndarray:
        z0 = generate_standard_normals(n, dim, int(spec.seed) + seed_off, spec.sampling_method)
        return apply_copula(z0 @ l.T, spec)

    if tg.dynamics == "iid":
        z = np.empty((n, dim, t_max), dtype=np.float64)
        for t in range(t_max):
            z[:, :, t] = step_innov(10_001 + t)
        return z

    if tg.dynamics == "ar1":
        phi = float(tg.ar1_phi)
        scale = float(np.sqrt(max(1e-12, 1.0 - phi**2)))
        z = np.empty((n, dim, t_max), dtype=np.float64)
        z[:, :, 0] = step_innov(0)
        for t in range(1, t_max):
            z[:, :, t] = phi * z[:, :, t - 1] + scale * step_innov(10_001 + t)
        return z

    raise ValueError(f"unknown path dynamics: {tg.dynamics}")


def build_shock_array(spec: ShockPackSpec) -> ShockArray:
    z = generate_correlated_z_paths(spec)
    n_periods = int(z.shape[2]) if z.ndim == 3 else 1
    return ShockArray(
        shockpack_id=spec.shockpack_id,
        seed=spec.seed,
        n_scenarios=spec.n_scenarios,
        factor_order=spec.factor_order,
        n_periods=n_periods,
        z=z,
    )
