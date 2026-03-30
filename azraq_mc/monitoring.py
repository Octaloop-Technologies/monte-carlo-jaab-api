from __future__ import annotations

from pathlib import Path

from azraq_mc.engine import run_adhoc_asset_simulation
from azraq_mc.schemas import AssetAssumptions, ShockPackSpec, SimulationResult
from azraq_mc.snapshots import save_snapshot


def run_scheduled_asset_simulation(
    shock_spec: ShockPackSpec,
    asset: AssetAssumptions,
    *,
    snapshot_root: Path | str,
    label: str | None = None,
    persist: bool = True,
    model_version: str = "azraq-mc-v1",
    include_attribution: bool = False,
    user_id: str | None = None,
) -> tuple[SimulationResult, Path | None]:
    """
    Mode 2 — scheduled monitoring: Monte Carlo refresh with optional JSON snapshot for drift tracking.
    """
    result = run_adhoc_asset_simulation(
        shock_spec,
        asset,
        model_version=model_version,
        include_attribution=include_attribution,
        execution_mode="scheduled_monitoring",
        user_id=user_id,
    )
    if not persist:
        return result, None
    path = save_snapshot(Path(snapshot_root), "asset_simulation", result, label=label)
    return result, path
