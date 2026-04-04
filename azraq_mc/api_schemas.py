from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, computed_field, model_validator

from azraq_mc.response_help import CALIBRATION_PREVIEW, SCHEDULED_ASSET_RESPONSE
from azraq_mc.schemas import (
    AssetAssumptions,
    BaseCaseResult,
    PortfolioSimulationResult,
    ShockPackSpec,
    SimulationResult,
    PerformanceProfile,
)


class AdhocSimulationRequest(BaseModel):
    shockpack: ShockPackSpec | None = None
    shockpack_catalog_entry_id: str | None = Field(
        default=None,
        description="Use registered artefact from /v1/shockpack/catalog (overrides inline shockpack body if both set)",
    )
    asset: AssetAssumptions
    include_attribution: bool = False
    include_advanced_attribution: bool = Field(
        default=False,
        description="If include_attribution: Euler covariance + Shapley-style incremental R² on CF loss",
    )
    attribution_tail_fraction: float = Field(default=0.05, ge=0.01, le=0.25)
    performance_profile: PerformanceProfile | None = Field(
        default=None,
        description="interactive caps n_scenarios≤5000 for faster UX; standard≤25000",
    )

    @model_validator(mode="after")
    def shockpack_or_catalog(self) -> AdhocSimulationRequest:
        if self.shockpack is None and self.shockpack_catalog_entry_id is None:
            raise ValueError("provide shockpack and/or shockpack_catalog_entry_id")
        return self


class PortfolioSimulationRequest(BaseModel):
    shockpack: ShockPackSpec | None = None
    shockpack_catalog_entry_id: str | None = None
    portfolio_id: str
    portfolio_assumption_set_id: str
    assets: list[AssetAssumptions] = Field(min_length=2)
    performance_profile: PerformanceProfile | None = None

    @model_validator(mode="after")
    def shockpack_or_catalog_portfolio(self) -> PortfolioSimulationRequest:
        if self.shockpack is None and self.shockpack_catalog_entry_id is None:
            raise ValueError("provide shockpack and/or shockpack_catalog_entry_id")
        return self


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

    @computed_field
    @property
    def response_help(self) -> dict[str, Any]:
        return dict(SCHEDULED_ASSET_RESPONSE)


class ShockExportRequest(BaseModel):
    shockpack: ShockPackSpec
    directory: str | None = Field(
        default=None, description="Folder for .npz + meta.json; defaults to AZRAQ_SHOCK_EXPORT_DIR or data/shockpacks"
    )


class CalibrationPreviewResponse(BaseModel):
    """Resolved `ShockPackSpec` after applying `dynamic_margins` (no simulation)."""

    resolved_shockpack: ShockPackSpec
    calibration_trace: dict[str, Any] | None = None

    @computed_field
    @property
    def response_help(self) -> dict[str, Any]:
        return dict(CALIBRATION_PREVIEW)
