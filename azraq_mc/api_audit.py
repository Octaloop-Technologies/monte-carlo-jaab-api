from __future__ import annotations

import os
from typing import Any

from azraq_mc.audit import log_simulation_run
from azraq_mc.schemas import BaseCaseResult, PortfolioSimulationResult, SimulationResult


def audit_simulation(
    run_kind: str,
    result: SimulationResult | PortfolioSimulationResult | BaseCaseResult,
    *,
    user_id: str | None = None,
    client_hint: str | None = None,
) -> None:
    if os.environ.get("AZRAQ_DISABLE_AUDIT", "").lower() in ("1", "true", "yes"):
        return
    payload: dict[str, Any] = result.model_dump(mode="json")
    hint = client_hint
    if user_id:
        hint = f"{hint + '|' if hint else ''}user:{user_id}"
    if isinstance(result, SimulationResult):
        m = result.metadata
        log_simulation_run(
            run_id=m.run_id,
            run_kind=run_kind,
            shockpack_id=m.shockpack_id,
            assumption_set_id=m.assumption_set_id,
            asset_id=m.asset_id,
            seed=m.seed,
            n_scenarios=m.n_scenarios,
            payload=payload,
            client_hint=hint,
        )
        return
    if isinstance(result, BaseCaseResult):
        m = result.metadata
        log_simulation_run(
            run_id=m.run_id,
            run_kind=run_kind,
            shockpack_id=m.shockpack_id,
            assumption_set_id=m.assumption_set_id,
            asset_id=m.asset_id,
            seed=m.seed,
            n_scenarios=m.n_scenarios,
            payload=payload,
            client_hint=hint,
        )
        return
    m = result.metadata
    log_simulation_run(
        run_id=m.run_id,
        run_kind=run_kind,
        shockpack_id=m.shockpack_id,
        assumption_set_id=m.assumption_set_id,
        portfolio_id=m.portfolio_id,
        seed=m.seed,
        n_scenarios=m.n_scenarios,
        payload=payload,
        client_hint=hint,
    )
