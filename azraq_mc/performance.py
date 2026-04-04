"""Sub-10s style interactive runs — scenario caps."""
from __future__ import annotations

from azraq_mc.schemas import PerformanceProfile, ShockPackSpec


def apply_performance_profile(spec: ShockPackSpec, profile: PerformanceProfile | None) -> ShockPackSpec:
    if profile is None or profile == "deep":
        return spec
    cap = 5000 if profile == "interactive" else 25_000
    n = min(spec.n_scenarios, cap)
    if n == spec.n_scenarios:
        return spec
    return spec.model_copy(update={"n_scenarios": n})
