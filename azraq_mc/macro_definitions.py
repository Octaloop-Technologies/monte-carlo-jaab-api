"""
§3.1.1 — First-class macro / market factor labels and risk-bucket taxonomy (§4.6).

Shock indices in `factor_order` map to buckets for attribution and documentation.
"""
from __future__ import annotations

from typing import Literal

# Six stakeholder-facing risk buckets (extend mappings as factors are added).
RiskBucket = Literal[
    "market_macro",
    "rates_funding",
    "energy_commodities",
    "delivery_regulatory",
    "infrastructure_physics",
    "operational_contract_cyber",
]

# Full-stack + 4-factor canonical names → bucket.
FACTOR_RISK_BUCKET: dict[str, RiskBucket] = {
    "revenue": "market_macro",
    "capex": "market_macro",
    "opex": "market_macro",
    "rate": "rates_funding",
    "fx": "market_macro",
    "power_price": "energy_commodities",
    "commodity_construction": "energy_commodities",
    "permit_regulatory": "delivery_regulatory",
    "weather": "delivery_regulatory",
    "grid_interconnection": "infrastructure_physics",
    "thermal_cooling": "infrastructure_physics",
    "cyber": "operational_contract_cyber",
}

# Macro labels for catalogue / regimes (documentation + future calibration binding).
MacroCurveLabel = Literal[
    "SOFR_3M",
    "SONIA_overnight",
    "UST_10Y",
    "FX_major_pair",
    "power_base_load",
    "commodity_cu",
    "commodity_steel",
    "inflation_cpi_headline",
    "inflation_ppi_construction",
]
