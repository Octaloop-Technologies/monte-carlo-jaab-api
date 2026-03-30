from __future__ import annotations

import numpy as np
import numpy_financial as npf

try:
    from numba import njit

    @njit(cache=True)
    def _npv_equity_scalar(eq0: float, cf: float, years: int, rate: float) -> float:
        npv = -eq0
        disc = 1.0
        for _ in range(years):
            disc *= 1.0 + rate
            npv += cf / disc
        return npv

    @njit(cache=True)
    def _irr_equity_batch(initial_equity: np.ndarray, annual_cf: np.ndarray, years: int) -> np.ndarray:
        n = initial_equity.shape[0]
        out = np.full(n, np.nan, dtype=np.float64)
        for i in range(n):
            eq0 = initial_equity[i]
            cf = annual_cf[i]
            if eq0 <= 1e-12:
                continue
            lo, hi = -0.9999, 5.0
            v_lo = _npv_equity_scalar(eq0, cf, years, lo)
            v_hi = _npv_equity_scalar(eq0, cf, years, hi)
            if v_lo * v_hi > 0:
                continue
            for _ in range(96):
                mid = 0.5 * (lo + hi)
                v_mid = _npv_equity_scalar(eq0, cf, years, mid)
                if abs(v_mid) < 1e-9 * max(1.0, abs(eq0)):
                    lo = hi = mid
                    break
                if v_mid * v_lo > 0:
                    lo = mid
                    v_lo = v_mid
                else:
                    hi = mid
            out[i] = 0.5 * (lo + hi)
        return out

    NUMBA_IRR_AVAILABLE = True
except Exception:
    NUMBA_IRR_AVAILABLE = False


def equity_irr_batch(initial_equity: np.ndarray, annual_cf: np.ndarray, years: int) -> np.ndarray:
    """Vectorised equity IRR; uses Numba when available."""
    initial_equity = np.asarray(initial_equity, dtype=np.float64)
    annual_cf = np.asarray(annual_cf, dtype=np.float64)
    if NUMBA_IRR_AVAILABLE:
        return _irr_equity_batch(initial_equity, annual_cf, int(years))
    n = initial_equity.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    for i in range(n):
        eq0 = float(initial_equity[i])
        if eq0 <= 0:
            continue
        cfs = np.empty(years + 1, dtype=np.float64)
        cfs[0] = -eq0
        cfs[1:] = float(annual_cf[i])
        try:
            r = npf.irr(cfs)
            out[i] = float(r) if r is not None and np.isfinite(r) else np.nan
        except (ValueError, FloatingPointError, TypeError):
            out[i] = np.nan
    return out
