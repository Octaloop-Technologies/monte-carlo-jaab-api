from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

SamplingMethod = Literal["monte_carlo", "latin_hypercube", "sobol"]
CopulaKind = Literal["gaussian", "student_t"]


class RiskFactorDefinition(BaseModel):
    """Appendix B.1 — documented risk factor (calibration metadata for ShockPacks)."""

    factor_id: str
    display_name: str = ""
    description: str = ""
    distribution_family: Literal["normal_shock", "derived"] = "normal_shock"
    calibration_version: str = "1.0"


class FullStackLayerConfig(BaseModel):
    """
    Deterministic cross-layer propagation parameters (delivery, physical, operational, cyber)
    applied on top of macro financial shocks. Randomness remains only in Z (ShockPack).
    """

    enabled: bool = True
    base_schedule_months: float = Field(default=18.0, gt=0, description="RFS-style delivery baseline (months)")
    permit_delay_sensitivity_months: float = Field(default=2.0, ge=0)
    weather_delay_sensitivity_months: float = Field(default=1.5, ge=0)
    grid_delay_sensitivity_months: float = Field(default=1.2, ge=0)
    capex_overrun_per_month_delay_fraction: float = Field(default=0.02, ge=0)
    fx_revenue_elasticity: float = Field(default=0.04, ge=0)
    fx_capex_elasticity: float = Field(default=0.06, ge=0)
    commodity_capex_elasticity: float = Field(default=0.05, ge=0)
    power_utility_elasticity: float = Field(default=0.08, ge=0, description="Maps power price shock → utility OPEX")
    power_revenue_pass_through: float = Field(default=0.02, ge=0)
    baseline_grid_outage_days: float = Field(default=2.0, ge=0)
    grid_stress_to_outage_days: float = Field(default=12.0, ge=0)
    thermal_failure_days_per_unit: float = Field(default=4.0, ge=0)
    backup_mitigation_factor: float = Field(default=0.35, ge=0, lt=1)
    sla_target_availability: float = Field(default=0.999, gt=0, lt=1)
    revenue_penalty_below_sla: float = Field(default=0.12, ge=0, le=1)
    tenant_concentration_top_share: float = Field(default=0.4, ge=0, le=1)
    tenant_default_probability_weight: float = Field(default=0.2, ge=0, le=1)
    tenant_revenue_stress_scale: float = Field(default=1.0, gt=0)
    cyber_event_threshold: float = Field(default=1.2)
    cyber_downtime_days: float = Field(default=10.0, ge=0)
    cyber_recovery_cost_fraction_of_capex: float = Field(default=0.015, ge=0)


class AssetFactorTransforms(BaseModel):
    """Layer 2 — asset-specific mapping from systemic shocks to effective paths (pure scalings in V1)."""

    revenue_shock_scale: float = Field(default=1.0, gt=0)
    capex_shock_scale: float = Field(default=1.0, gt=0)
    opex_shock_scale: float = Field(default=1.0, gt=0)
    rate_shock_scale: float = Field(default=1.0, gt=0)
    revenue_level_multiplier: float = Field(default=1.0, gt=0, description="Regional / market scaling on revenue")
    capex_level_multiplier: float = Field(
        default=1.0, gt=0, description="Design sensitivity / contingency on effective capex exposure"
    )
    opex_level_multiplier: float = Field(default=1.0, gt=0)
    mitigation_dscr_floor: float | None = Field(
        default=None,
        gt=0,
        description="Post-process floor on DSCR (e.g., DSCR LC provider / DSRA mechanics, highly stylised)",
    )


class FinancingAssumptions(BaseModel):
    """Debt and covenant parameters (deterministic structure; rate shock comes from ShockPack)."""

    debt_principal: float = Field(
        ge=0, description="Initial drawn principal; use 0 for equity-only (IRR unlevered at equity=100%)"
    )
    interest_rate_annual: float = Field(ge=0, lt=1, description="Base annual all-in coupon (decimal)")
    loan_term_years: int = Field(ge=1)
    covenant_dscr: float = Field(default=1.2, gt=0, description="Breach if DSCR below this level")


class AssetAssumptions(BaseModel):
    """Single-asset operating and capital inputs (V1 financial layer)."""

    asset_id: str
    assumption_set_id: str
    horizon_years: int = Field(ge=1, description="Operating years for cashflow / IRR")
    base_revenue_annual: float = Field(gt=0)
    base_opex_annual: float = Field(ge=0)
    initial_capex: float = Field(gt=0)
    equity_fraction: float = Field(gt=0, le=1, description="Equity share of initial capex (1.0 = no debt)")
    tax_rate: float = Field(default=0.0, ge=0, lt=1)
    financing: FinancingAssumptions
    equity_discount_rate_for_npv: float | None = Field(
        default=None,
        ge=0,
        lt=1,
        description="Optional discount rate for V0 equity NPV (same units as IRR); if unset, NPV omitted",
    )
    utility_opex_annual: float = Field(
        default=0.0,
        ge=0,
        description="Utility portion of OPEX (power, water) reported separately; must be ≤ base_opex_annual",
    )
    project_discount_rate_for_ev: float | None = Field(
        default=None,
        ge=0,
        lt=1,
        description="Unlevered project discount for stylised Enterprise Value (NPV of EBITDA after tax, ex-debt)",
    )
    factor_transforms: AssetFactorTransforms | None = None
    full_stack: FullStackLayerConfig | None = Field(
        default=None,
        description="Enable multi-layer delivery / physical / operational / cyber propagation (requires 12-factor ShockPack)",
    )

    @model_validator(mode="after")
    def utility_le_base(self):
        if self.utility_opex_annual > self.base_opex_annual + 1e-9:
            raise ValueError("utility_opex_annual cannot exceed base_opex_annual")
        return self


class RiskFactorMargins(BaseModel):
    """Marginal uncertainty for the V1 financial factor block (lognormal multipliers + additive rate shock)."""

    revenue_log_mean: float = 0.0
    revenue_log_sigma: float = Field(default=0.08, gt=0)
    capex_log_mean: float = 0.0
    capex_log_sigma: float = Field(default=0.06, gt=0)
    opex_log_mean: float = 0.0
    opex_log_sigma: float = Field(default=0.05, gt=0)
    rate_shock_sigma: float = Field(
        default=0.005,
        ge=0,
        description="Std dev of additive shock to annual interest rate (decimal, e.g. 0.005 = 50 bps typical)",
    )


class ShockPackSpec(BaseModel):
    """Defines correlated shocks only; versioning and storage are application concerns."""

    shockpack_id: str
    schema_version: str = "1.0"
    seed: int
    n_scenarios: int = Field(ge=100, le=500_000)
    sampling_method: SamplingMethod = "monte_carlo"
    factor_order: tuple[str, ...] = ("revenue", "capex", "opex", "rate")
    correlation: list[list[float]] = Field(
        default_factory=lambda: [
            [1.0, 0.35, 0.25, 0.15],
            [0.35, 1.0, 0.45, 0.1],
            [0.25, 0.45, 1.0, 0.05],
            [0.15, 0.1, 0.05, 1.0],
        ]
    )
    margins: RiskFactorMargins = Field(default_factory=RiskFactorMargins)
    copula: CopulaKind = Field(
        default="gaussian",
        description="Gaussian = correlated normals; student_t = multivariate-t style scaling for fatter tails",
    )
    t_degrees_freedom: float = Field(default=8.0, gt=2)

    @field_validator("correlation")
    @classmethod
    def square_psd(cls, m: list[list[float]]) -> list[list[float]]:
        n = len(m)
        if any(len(row) != n for row in m):
            raise ValueError("correlation must be square")
        return m

    @model_validator(mode="after")
    def correlation_matches_factor_order(self):
        if len(self.factor_order) != len(self.correlation):
            raise ValueError("factor_order length must equal correlation matrix dimension")
        return self


class ShockArray(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    shockpack_id: str
    seed: int
    n_scenarios: int
    factor_order: tuple[str, ...]
    # shape (n_scenarios, n_factors)—standard correlated normal draws before marginals
    z: object


ExecutionMode = Literal["adhoc_asset", "portfolio_joint", "scheduled_monitoring", "v0_base"]


class SimulationRunMetadata(BaseModel):
    run_id: str
    shockpack_id: str
    assumption_set_id: str
    asset_id: str
    model_version: str
    seed: int
    n_scenarios: int
    sampling_method: SamplingMethod
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    execution_mode: ExecutionMode = "adhoc_asset"
    user_id: str | None = Field(default=None, description="Optional operator / principal id for audit")
    layer_versions: dict[str, str] | None = Field(default=None, description="Semantic versions per engine layer")


class DistributionSummary(BaseModel):
    p05: float
    p10: float
    p50: float
    p90: float
    p95: float
    mean: float
    std: float


class FinancialRiskMetrics(BaseModel):
    dscr: DistributionSummary
    irr_annual: DistributionSummary | None
    covenant_breach_probability: float = Field(ge=0, le=1)
    probability_of_default_proxy_dscr_lt_1: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Stylised P(DSCR<1.0); not a ratings PD without calibration",
    )
    var_irr_95: float | None = Field(
        default=None,
        description="Difference vs median IRR at 5th percentile (loss side), same units as IRR",
    )
    cvar_irr_95: float | None = Field(
        default=None, description="Mean IRR in the worst 5% of scenarios (simple average below p05)"
    )


class FactorAttributionResult(BaseModel):
    """Simple tail-regression attribution of correlated shocks to DSCR in bad scenarios."""

    target: str = "dscr"
    tail_fraction: float = Field(ge=0.01, le=0.5)
    n_tail_scenarios: int = Field(ge=0)
    factor_order: tuple[str, ...]
    standardized_beta: dict[str, float] = Field(default_factory=dict)
    share_of_abs_beta: dict[str, float] = Field(
        default_factory=dict, description="Normalised |beta| shares summing to ~1"
    )
    r_squared: float | None = None


class FullStackMetrics(BaseModel):
    """Cross-layer outcome summaries when AssetAssumptions.full_stack is enabled."""

    schedule_delay_months: DistributionSummary
    critical_path_completion_months: DistributionSummary
    downtime_days: DistributionSummary
    availability: DistributionSummary
    probability_sla_breach: float = Field(ge=0, le=1)
    probability_cyber_material: float = Field(ge=0, le=1, description="Mean(cyber severity)≈P(material event)")
    milestone_completion: dict[str, float] = Field(
        default_factory=dict,
        description="Keys like by_month_12 → P(critical path completes by horizon)",
    )


class SimulationResult(BaseModel):
    metadata: SimulationRunMetadata
    metrics: FinancialRiskMetrics
    attribution: FactorAttributionResult | None = None
    full_stack: FullStackMetrics | None = None


class BaseCaseMetrics(BaseModel):
    """V0 deterministic point estimates (zero shock / median factors)."""

    dscr: float
    irr_annual: float | None
    annual_revenue: float = Field(description="Steady-state revenue after multipliers")
    ebitda: float
    debt_service: float
    initial_equity: float
    utility_opex_exposure: float = Field(
        default=0.0, description="Utility OPEX after same OPEX shock path as consolidated OPEX"
    )
    revenue_multiplier: float
    capex_multiplier: float
    opex_multiplier: float
    effective_interest_rate: float
    npv_equity: float | None = None
    enterprise_value: float | None = Field(
        default=None,
        description="Stylised unlevered EV = NPV(project FCF) at project_discount_rate_for_ev if provided",
    )


class BaseCaseResult(BaseModel):
    metadata: SimulationRunMetadata
    base: BaseCaseMetrics


class PortfolioRunMetadata(BaseModel):
    run_id: str
    portfolio_id: str
    assumption_set_id: str
    shockpack_id: str
    model_version: str
    seed: int
    n_scenarios: int
    sampling_method: SamplingMethod
    asset_ids: list[str]
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    execution_mode: ExecutionMode = "portfolio_joint"
    user_id: str | None = None
    layer_versions: dict[str, str] | None = None


class PerAssetMetrics(BaseModel):
    asset_id: str
    assumption_set_id: str
    metrics: FinancialRiskMetrics


class PortfolioMetrics(BaseModel):
    n_assets: int
    scenarios: int
    probability_any_covenant_breach: float = Field(ge=0, le=1)
    probability_at_least_k_breaches: dict[str, float] = Field(
        default_factory=dict, description='Keys "2","3",… as strings for JSON stability'
    )
    min_dscr_across_assets: DistributionSummary
    sum_levered_cf_year1: DistributionSummary
    var_sum_levered_cf_p05: float | None = Field(
        default=None, description="5th percentile of summed Year-1 levered CF after tax (downside)"
    )
    cvar_sum_levered_cf_p05: float | None = Field(
        default=None, description="Mean of summed CF in scenarios at or below the 5th percentile"
    )
    revenue_herfindahl: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="∑wᵢ² with wᵢ ∝ base revenue — concentration of revenue across assets",
    )
    weighted_covenant_breach_exposure: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="E[∑ wᵢ · 1(breachᵢ)] — revenue-weighted simultaneous covenant stress",
    )


class PortfolioSimulationResult(BaseModel):
    metadata: PortfolioRunMetadata
    per_asset: list[PerAssetMetrics]
    portfolio: PortfolioMetrics


class SavedSnapshot(BaseModel):
    """On-disk snapshot row (body is JSON object; use snapshot_load_typed to rehydrate)."""

    version: Literal[1] = 1
    kind: Literal["asset_simulation", "portfolio_simulation", "v0_base"]
    label: str | None = None
    saved_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    body: dict[str, Any]
