"""CLI demo and ASGI entrypoint (``uvicorn main:app``)."""

from __future__ import annotations

import json

from azraq_mc.api import app  # noqa: F401  — exposed for Uvicorn: `uvicorn main:app`
from azraq_mc.engine import run_adhoc_asset_simulation
from azraq_mc.schemas import AssetAssumptions, FinancingAssumptions, ShockPackSpec


def demo() -> None:
    asset = AssetAssumptions(
        asset_id="dc-fra-01",
        assumption_set_id="demo-2026Q1",
        horizon_years=15,
        base_revenue_annual=42e6,
        base_opex_annual=18e6,
        initial_capex=280e6,
        equity_fraction=0.35,
        tax_rate=0.0,
        financing=FinancingAssumptions(
            debt_principal=182e6,
            interest_rate_annual=0.065,
            loan_term_years=18,
            covenant_dscr=1.2,
        ),
    )
    shock = ShockPackSpec(
        shockpack_id="eu-west-macro-v3",
        seed=42,
        n_scenarios=20_000,
        sampling_method="monte_carlo",
    )
    result = run_adhoc_asset_simulation(shock, asset)
    print(json.dumps(result.model_dump(mode="json"), indent=2, default=str))


if __name__ == "__main__":
    demo()
