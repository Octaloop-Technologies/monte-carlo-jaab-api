from __future__ import annotations

import numpy as np

from azraq_mc.schemas import RiskFactorDefinition, ShockPackSpec

FULL_STACK_FACTOR_ORDER = (
    "revenue",
    "capex",
    "opex",
    "rate",
    "fx",
    "power_price",
    "commodity_construction",
    "permit_regulatory",
    "weather",
    "grid_interconnection",
    "thermal_cooling",
    "cyber",
)

REQUIRED_LAYER_FACTORS = frozenset(FULL_STACK_FACTOR_ORDER)


FULL_STACK_RISK_FACTOR_CATALOG: list[RiskFactorDefinition] = [
    RiskFactorDefinition(
        factor_id="revenue",
        display_name="Market demand / colo pricing",
        description="Macro demand and pricing shocks translated into revenue paths.",
    ),
    RiskFactorDefinition(
        factor_id="capex",
        display_name="Capex inflation / delivery cost",
        description="Construction & equipment inflation, supply-chain stress.",
    ),
    RiskFactorDefinition(factor_id="opex", display_name="Opex inflation", description="General operating cost inflation."),
    RiskFactorDefinition(
        factor_id="rate",
        display_name="Interest rates",
        description="SOFR/SONIA-like funding shock on debt service.",
    ),
    RiskFactorDefinition(factor_id="fx", display_name="FX", description="FX exposure on equipment / revenue."),
    RiskFactorDefinition(
        factor_id="power_price",
        display_name="Electricity / PPA price",
        description="Utility and PPA-linked price volatility.",
    ),
    RiskFactorDefinition(
        factor_id="commodity_construction",
        display_name="Construction commodities",
        description="Copper, steel, and related hard-cost drivers.",
    ),
    RiskFactorDefinition(
        factor_id="permit_regulatory",
        display_name="Permitting & regulatory timing",
        description="Permit / grid / regulatory delay shocks (delivery layer).",
    ),
    RiskFactorDefinition(
        factor_id="weather",
        display_name="Weather / constructability",
        description="Weather loss days impacting critical path.",
    ),
    RiskFactorDefinition(
        factor_id="grid_interconnection",
        display_name="Grid interconnection stress",
        description="Grid delay and reliability stress.",
    ),
    RiskFactorDefinition(
        factor_id="thermal_cooling",
        display_name="Cooling / thermal margin",
        description="Thermal stress impacting failure rates and efficiency.",
    ),
    RiskFactorDefinition(
        factor_id="cyber",
        display_name="Cyber / technology risk",
        description="Cyber event stress for downtime and recovery costs.",
    ),
]


def default_full_stack_correlation() -> list[list[float]]:
    """12×12 PSD correlation—macro + market + delivery + infrastructure + cyber (stylised)."""
    # Construct SPD via low-rank + diagonal (guarantees PSD)
    rng = np.random.default_rng(42)
    k = 6
    u = rng.standard_normal((12, k))
    c = np.dot(u, u.T) / k
    d = np.sqrt(np.clip(1.0 - np.diag(c), 0.05, None))
    corr = c + np.diag(d)
    # Normalise to unit diagonal
    inv_sd = 1.0 / np.sqrt(np.diag(corr))
    corr = (inv_sd[:, None] * corr) * inv_sd[None, :]
    corr = np.clip(corr, -0.95, 0.95)
    np.fill_diagonal(corr, 1.0)
    return corr.tolist()


def make_full_stack_shockpack(
    shockpack_id: str,
    seed: int,
    n_scenarios: int,
    **kwargs: object,
) -> ShockPackSpec:
    return ShockPackSpec(
        shockpack_id=shockpack_id,
        seed=seed,
        n_scenarios=n_scenarios,
        factor_order=FULL_STACK_FACTOR_ORDER,
        correlation=default_full_stack_correlation(),
        **kwargs,
    )
