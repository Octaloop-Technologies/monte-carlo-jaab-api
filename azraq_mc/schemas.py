from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from azraq_mc.response_help import (
    BASE_CASE_RESULT,
    PORTFOLIO_SIMULATION_RESULT,
    SIMULATION_RESULT,
)

SamplingMethod = Literal["monte_carlo", "latin_hypercube", "sobol"]
CopulaKind = Literal["gaussian", "student_t"]
PathDynamics = Literal["iid", "ar1"]
PerformanceProfile = Literal["interactive", "standard", "deep"]


class TimeGridSpec(BaseModel):
    """§3.2 — Multi-period shock paths (granularity over the model horizon)."""

    n_periods: int = Field(default=1, ge=1, le=120)
    period_length_years: float = Field(
        default=1.0,
        gt=0,
        description="Length of one step in years (e.g. 0.25 = quarterly)",
    )
    dynamics: PathDynamics = Field(
        default="iid",
        description="iid: independent draws per period; ar1: AR(1) persistence per factor",
    )
    ar1_phi: float = Field(
        default=0.65,
        ge=0.0,
        lt=1.0,
        description="AR(1) coefficient when dynamics=ar1",
    )


class MacroTermStructureSpec(BaseModel):
    """§3.1.1 — Tenor knots and loadings for parallel rate shocks (SOFR ladder–style aggregate)."""

    tenor_years: tuple[float, ...] = Field(
        default=(0.25, 1.0, 3.0, 5.0, 10.0, 30.0),
        description="Benchmark curve points in years",
    )
    loadings: tuple[float, ...] | None = Field(
        default=None,
        description="Weights on each tenor for effective shock; None = equal weights",
    )
    parallel_vol_multipliers: tuple[float, ...] | None = Field(
        default=None,
        description="Optional per-tenor vol vs unit benchmark; None = ones",
    )
    rate_factor_key: str = Field(default="rate", description="factor_order id for the parallel driver")

    @model_validator(mode="after")
    def _macro_lengths(self):
        n = len(self.tenor_years)
        if self.loadings is not None and len(self.loadings) != n:
            raise ValueError("macro_term_structure.loadings must match tenor_years length")
        if self.parallel_vol_multipliers is not None and len(self.parallel_vol_multipliers) != n:
            raise ValueError("parallel_vol_multipliers must match tenor_years length")
        return self


class InflationProcessSpec(BaseModel):
    """Separate inflation channel mapped through an existing factor draw (first-class pass-through)."""

    enabled: bool = False
    z_factor_key: str = Field(default="opex", description="Which ShockPack column drives log inflation innovation")
    log_sigma: float = Field(default=0.02, ge=0)
    opex_beta: float = Field(default=1.0, ge=0)
    capex_beta: float = Field(default=0.35, ge=0)
    revenue_beta: float = Field(default=0.0, ge=0)


class CpmTaskShockLink(BaseModel):
    """Map a positive shock draw to extra months of duration for one task."""

    factor_id: str
    months_per_positive_z: float = Field(default=0.0, ge=0)


class CpmTaskSpec(BaseModel):
    """One node in a delivery CPM graph (§3.3)."""

    task_id: str
    duration_base_months: float = Field(gt=0)
    predecessor_ids: tuple[str, ...] = Field(default_factory=tuple)
    shock_links: tuple[CpmTaskShockLink, ...] = Field(default_factory=tuple)
    resource_id: str | None = Field(default=None, description="Optional crew / equipment pool id")
    resource_units: float = Field(default=1.0, gt=0, description="Demand on resource_id per task")


class CpmResourcePool(BaseModel):
    """Calendar / capacity for CPM resource levelling."""

    resource_id: str
    capacity_units: float = Field(gt=0, description="Effective crew-months (or normalized units) per horizon")
    calendar_efficiency: float = Field(default=1.0, gt=0, le=1)


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
    cpm_tasks: tuple[CpmTaskSpec, ...] = Field(
        default_factory=tuple,
        description="If non-empty, replaces aggregate permit/weather/grid delay with DAG critical-path months",
    )
    generator_failure_conditional_days: float = Field(
        default=0.0,
        ge=0,
        description="Extra outage days when grid stress and thermal stress coincide (backup failure proxy)",
    )
    baseline_pue: float = Field(default=1.35, gt=1, description="Baseline PUE before thermal stress")
    pue_target: float = Field(default=1.5, gt=1)
    baseline_wue: float = Field(default=1.4, ge=0, description="Baseline WUE before stress")
    wue_target: float | None = Field(default=None, ge=0, description="l/kWh style; optional breach stat")
    pue_stress_sensitivity: float = Field(default=0.12, ge=0, description="PUE uplift per unit thermal shock")
    wue_stress_sensitivity: float = Field(default=50.0, ge=0)
    contract_churn_revenue_elasticity: float = Field(
        default=0.08,
        ge=0,
        description="Extra revenue drag from legal/churn shock mapped to -relu(z_revenue)",
    )
    cpm_resource_pools: tuple[CpmResourcePool, ...] = Field(
        default_factory=tuple,
        description="When set with task resource_id, stretches critical path for contention",
    )
    mttf_hours: float = Field(default=8760.0, gt=0, description="MTTF for Markov availability overlay")
    mttr_hours: float = Field(
        default=0.0,
        ge=0,
        description="MTTR hours; 0 disables reliability overlay",
    )
    reliability_availability_weight: float = Field(
        default=0.0,
        ge=0,
        le=1,
        description="Blend factor for extra downtime from MTTF/MTTR derating",
    )


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
        description="Per-period floor when DSRA / LC stylised mechanics enabled via waterfall",
    )


class FinancingAssumptions(BaseModel):
    """Debt and covenant parameters (deterministic structure; rate shock comes from ShockPack)."""

    debt_principal: float = Field(
        ge=0, description="Initial drawn principal; use 0 for equity-only (IRR unlevered at equity=100%)"
    )
    interest_rate_annual: float = Field(ge=0, lt=1, description="Base annual all-in coupon (decimal)")
    loan_term_years: int = Field(ge=1)
    covenant_dscr: float = Field(default=1.2, gt=0, description="Breach if DSCR below this level")


class DebtTrancheSpec(BaseModel):
    """Seniority slice for weighted coupon and waterfall metadata."""

    tranche_id: str
    seniority_rank: int = Field(default=0, ge=0, description="0 = most senior cash trap")
    share_of_debt: float = Field(gt=0, le=1, description="Share of drawn principal")
    coupon_spread_add: float = Field(default=0.0, ge=0, lt=0.2, description="Additive to base coupon, decimal")


class WaterfallAssumptions(BaseModel):
    """DSRA / LC / sculpting hooks (stylised; not a full 3-statement model)."""

    enabled: bool = False
    tranches: tuple[DebtTrancheSpec, ...] = Field(default_factory=tuple)
    dsra_months_of_debt_service: float = Field(default=0.0, ge=0)
    dsra_funding_speed: float = Field(
        default=0.35,
        ge=0,
        le=1,
        description="Fraction of target DSRA build charged per year (linear ramp proxy)",
    )
    lc_commitment_fee_annual_pct: float = Field(default=0.0, ge=0, lt=0.05)
    sculpt_target_dscr: float | None = Field(
        default=None,
        gt=0,
        description="When set (multi-period paths), per-period debt service capped by EBITDA / target",
    )


class LiquidityAssumptions(BaseModel):
    """Buffers for runway-style metrics."""

    enabled: bool = False
    minimum_cash_months_opex: float = Field(default=3.0, ge=0)
    cash_buffer_fixed: float = Field(default=0.0, ge=0)


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
    waterfall: WaterfallAssumptions | None = Field(default=None, description="Tranche / DSRA / LC / sculpting")
    liquidity: LiquidityAssumptions | None = Field(default=None)

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


MarginSigmaField = Literal["revenue_log_sigma", "capex_log_sigma", "opex_log_sigma", "rate_shock_sigma"]


class MarginCalibrationFileSource(BaseModel):
    """Load margin fields from a JSON file or Excel workbook (partial map or full `RiskFactorMargins` shape)."""

    path: str = Field(description="Filesystem path; relative paths resolve from the process working directory")
    mode: Literal["overlay", "replace"] = Field(
        default="overlay",
        description="overlay: patch only provided keys onto `margins`; replace: use file object as full margins",
    )
    sheet: str | int = Field(
        default=0,
        description="Excel only: sheet name or 0-based index. Ignored for `.json` files.",
    )


class MarginCalibrationHttpSource(BaseModel):
    """GET JSON from a URL; body is either a flat margin map or `{\"margins\": {...}}`."""

    url: str
    timeout_sec: float = Field(default=30.0, gt=0, le=120)
    headers: dict[str, str] = Field(default_factory=dict)
    mode: Literal["overlay", "replace"] = "overlay"


class YahooFinanceVolBinding(BaseModel):
    """
    Calibrate a `*_log_sigma` (or `rate_shock_sigma`) from realised close-to-close volatility.
    Uses log returns; annualises by `sqrt(annualization_factor)`.
    """

    symbol: str
    period: str = Field(
        default="1y",
        description="yfinance history period: 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max",
    )
    target: MarginSigmaField
    scale: float = Field(default=1.0, gt=0, description="Multiplier after annualisation (tweak units / conservatism)")
    annualization_factor: float = Field(
        default=252.0,
        gt=0,
        description="Bars per year for sqrt scaling (e.g. 252 for daily equity, 12 for monthly)",
    )
    min_observations: int = Field(default=20, ge=5, description="Minimum return samples required")


class DynamicMarginsSpec(BaseModel):
    """
    Optional sources that populate `ShockPackSpec.margins` before simulation.
    Order: `file` → `http` → each `yahoo_finance` binding (later steps override the same keys).
    Stripped from the copy returned by `materialize_shockpack_margins` so caches fingerprint resolved numbers.
    """

    file: MarginCalibrationFileSource | None = None
    http: MarginCalibrationHttpSource | None = None
    yahoo_finance: list[YahooFinanceVolBinding] = Field(default_factory=list)


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
    dynamic_margins: DynamicMarginsSpec | None = Field(
        default=None,
        description="Optional: pull margin parameters from file, HTTP JSON, or Yahoo Finance before running",
    )
    copula: CopulaKind = Field(
        default="gaussian",
        description="Gaussian = correlated normals; student_t = multivariate-t style scaling for fatter tails",
    )
    t_degrees_freedom: float = Field(default=8.0, gt=2)
    time_grid: TimeGridSpec | None = Field(
        default=None,
        description="If set with n_periods>1, Z has shape (n_scenarios, n_factors, n_periods)",
    )
    macro_regime: str = Field(
        default="baseline",
        description="Named macro regime for audit / ShockPack catalogue (e.g. disinflation, rates_shock)",
    )
    macro_term_structure: MacroTermStructureSpec | None = Field(
        default=None,
        description="Optional tenor ladder aggregation for the benchmark rate factor",
    )
    inflation_process: InflationProcessSpec | None = Field(
        default=None,
        description="Optional inflation pass-through layered on factor draws",
    )

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
    n_periods: int = 1
    # shape (n_scenarios, n_factors) or (n_scenarios, n_factors, n_periods)
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
    margin_calibration_trace: dict[str, Any] | None = Field(
        default=None,
        description="When dynamic_margins was used: sources applied and resolved values for audit",
    )
    shockpack_catalog_entry_id: str | None = Field(
        default=None, description="Registered artefact id when using ShockPack catalogue"
    )
    compute_time_ms: float | None = Field(default=None, description="Server-side wall time for the run")
    performance_profile: PerformanceProfile | None = Field(
        default=None, description="interactive caps scenarios for sub-10s style runs"
    )


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
    ebitda: DistributionSummary | None = Field(default=None, description="Mean-over-period EBITDA per scenario")
    var_ebitda_95: float | None = Field(
        default=None, description="Median minus p05 EBITDA (downside width), same units as EBITDA",
    )
    cvar_ebitda_95: float | None = Field(
        default=None, description="Mean EBITDA in worst 5% of scenarios (relative to churn)",
    )
    levered_cf: DistributionSummary | None = Field(
        default=None, description="After-tax levered cash flow (single-period / mean-period view)"
    )
    var_levered_cf_95: float | None = None
    cvar_levered_cf_95: float | None = None
    nav_proxy_equity: DistributionSummary | None = Field(
        default=None,
        description="Stylised terminal equity value = initial_equity + horizon * mean annual levered CF",
    )
    var_nav_proxy_95: float | None = None
    cvar_nav_proxy_95: float | None = None
    liquidity_runway_months: DistributionSummary | None = Field(
        default=None,
        description="Months of liquidity buffer / mean shortfall (requires liquidity + waterfall context)",
    )
    merton_equity_pd_proxy: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Structural PD heuristic from DSCR distribution (not a rating-agency PD)",
    )
    waterfall_dsra_avg_drag: float | None = Field(
        default=None,
        ge=0,
        description="Mean annual DSRA funding proxy when waterfall enabled",
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
    bucket_shares: dict[str, float] = Field(
        default_factory=dict,
        description="Aggregated |beta| share by risk bucket (market_macro, rates_funding, …)",
    )
    interaction_top_pair: tuple[str, str] | None = Field(
        default=None, description="Largest pairwise |Z_i Z_j| interaction in tail (heuristic)"
    )
    interaction_score: float | None = Field(default=None, description="Mean |z_i z_j| for the top pair in tail")
    var_metric_decomposition: dict[str, float] = Field(
        default_factory=dict,
        description="Unnormalised Δloss contribution vs median levered CF in tail (rough factor marginal)"
    )
    euler_risk_contributions: dict[str, float] = Field(
        default_factory=dict,
        description="Normalised |cov(loss,z)| shares (Euler-style linear marginal)",
    )
    shapley_risk_contributions: dict[str, float] = Field(
        default_factory=dict,
        description="Incremental R² Shapley-style weights on downside loss",
    )


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
    probability_pue_breach: float = Field(
        default=0.0, ge=0, le=1, description="P(PUE exceeds target after thermal stress)"
    )
    probability_wue_breach: float = Field(
        default=0.0, ge=0, le=1, description="P(WUE exceeds target if target set)"
    )
    grid_gen_joint_stress_days: DistributionSummary | None = Field(
        default=None, description="Proxy extra downtime from conditional gen/grid stress"
    )


class SimulationResult(BaseModel):
    metadata: SimulationRunMetadata
    metrics: FinancialRiskMetrics
    attribution: FactorAttributionResult | None = None
    full_stack: FullStackMetrics | None = None
    extensions: dict[str, Any] | None = Field(
        default=None,
        description="Macro curve report, tranche metadata, cache keys, etc.",
    )

    @computed_field
    @property
    def response_help(self) -> dict[str, Any]:
        """Plain-language guide to this JSON for clients and non-technical readers."""
        return dict(SIMULATION_RESULT)


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

    @computed_field
    @property
    def response_help(self) -> dict[str, Any]:
        return dict(BASE_CASE_RESULT)


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
    margin_calibration_trace: dict[str, Any] | None = None
    shockpack_catalog_entry_id: str | None = None
    compute_time_ms: float | None = None
    performance_profile: PerformanceProfile | None = None


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

    @computed_field
    @property
    def response_help(self) -> dict[str, Any]:
        return dict(PORTFOLIO_SIMULATION_RESULT)


class SavedSnapshot(BaseModel):
    """On-disk snapshot row (body is JSON object; use snapshot_load_typed to rehydrate)."""

    version: Literal[1] = 1
    kind: Literal["asset_simulation", "portfolio_simulation", "v0_base"]
    label: str | None = None
    saved_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    body: dict[str, Any]
