"""Two-state availability overlay from MTTF/MTTR (§4.x equipment reliability sketch)."""
from __future__ import annotations

import numpy as np


def stationary_uptime_fraction(mttf_hours: float, mttr_hours: float) -> float:
    if mttf_hours <= 0:
        return 1.0
    if mttr_hours <= 0:
        return 1.0
    return float(mttf_hours / (mttf_hours + mttr_hours))


def stress_derated_downtime_days(
    z_stress: np.ndarray,
    mttf_hours: float,
    mttr_hours: float,
    weight: float,
    baseline_excess_days: np.ndarray,
) -> np.ndarray:
    """
    Blend Markov stationary downtime with stress: increases outage days when z_stress>0.
    """
    if weight <= 0 or mttr_hours <= 0:
        return baseline_excess_days
    a0 = stationary_uptime_fraction(mttf_hours, mttr_hours)
    zs = np.asarray(z_stress, dtype=np.float64)
    stress = np.clip(0.15 * np.maximum(0.0, zs), 0.0, 0.6)
    derated = a0 * (1.0 - stress)
    markov_days = (1.0 - derated) * 365.0
    b = np.asarray(baseline_excess_days, dtype=np.float64)
    return b + weight * np.maximum(0.0, markov_days - (1.0 - a0) * 365.0)
