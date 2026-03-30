from pydantic import BaseModel, Field

from azraq_mc.schemas import (
    AssetAssumptions,
    BaseCaseResult,
    PortfolioSimulationResult,
    ShockPackSpec,
    SimulationResult,
)


class AdhocSimulationRequest(BaseModel):
    shockpack: ShockPackSpec
    asset: AssetAssumptions
    include_attribution: bool = False
    attribution_tail_fraction: float = Field(default=0.05, ge=0.01, le=0.25)


class PortfolioSimulationRequest(BaseModel):
    shockpack: ShockPackSpec
    portfolio_id: str
    portfolio_assumption_set_id: str
    assets: list[AssetAssumptions] = Field(min_length=2)


class SnapshotSaveRequest(BaseModel):
    label: str | None = None
    result: SimulationResult | PortfolioSimulationResult | BaseCaseResult


class ScheduledAssetRequest(AdhocSimulationRequest):
    label: str | None = None
    persist: bool = True
    model_version: str = "azraq-mc-v1"


class ScheduledAssetResponse(BaseModel):
    result: SimulationResult
    snapshot_path: str | None = None


class ShockExportRequest(BaseModel):
    shockpack: ShockPackSpec
    directory: str | None = Field(
        default=None, description="Folder for .npz + meta.json; defaults to AZRAQ_SHOCK_EXPORT_DIR or data/shockpacks"
    )
