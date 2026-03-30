from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from azraq_mc.presets import REQUIRED_LAYER_FACTORS
from azraq_mc.schemas import FullStackLayerConfig


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


def _relu(x: np.ndarray) -> np.ndarray:
    return np.maximum(0.0, x)


@dataclass
class FullStackAdjustment:
    revenue_mult: np.ndarray
    capex_mult: np.ndarray
    opex_mult: np.ndarray
    utility_price_mult: np.ndarray


@dataclass
class LayerDiagnostics:
    schedule_delay_months: np.ndarray
    critical_path_completion_months: np.ndarray
    downtime_days: np.ndarray
    availability: np.ndarray
    cyber_severity: np.ndarray
    sla_breach: np.ndarray


def _factor_index(factor_order: tuple[str, ...], name: str) -> int:
    try:
        return list(factor_order).index(name)
    except ValueError as e:
        raise ValueError(f"missing factor {name} in ShockPack factor_order for full_stack") from e


def validate_full_stack_factors(factor_order: tuple[str, ...]) -> None:
    missing = REQUIRED_LAYER_FACTORS - set(factor_order)
    if missing:
        raise ValueError(f"full_stack ShockPack missing factors: {sorted(missing)}")


def apply_full_stack_layers(
    z: np.ndarray,
    factor_order: tuple[str, ...],
    cfg: FullStackLayerConfig,
) -> tuple[FullStackAdjustment, LayerDiagnostics]:
    """
    Deterministic cross-layer propagation (§3.3 / §4.1–4.4):
    delivery → physical → operational (+ cyber, power pass-through) as multipliers on financials.
    """
    validate_full_stack_factors(factor_order)
    z = np.asarray(z, dtype=np.float64)
    n = z.shape[0]
    idx = {name: _factor_index(factor_order, name) for name in REQUIRED_LAYER_FACTORS}

    z_fx = z[:, idx["fx"]]
    z_power = z[:, idx["power_price"]]
    z_com = z[:, idx["commodity_construction"]]
    z_perm = z[:, idx["permit_regulatory"]]
    z_wea = z[:, idx["weather"]]
    z_grid = z[:, idx["grid_interconnection"]]
    z_therm = z[:, idx["thermal_cooling"]]
    z_cyb = z[:, idx["cyber"]]
    z_rev = z[:, idx["revenue"]]

    # --- 4.1 Delivery / expansion (critical-path style aggregate delay in months)
    delay = (
        cfg.permit_delay_sensitivity_months * _relu(z_perm)
        + cfg.weather_delay_sensitivity_months * _relu(z_wea)
        + cfg.grid_delay_sensitivity_months * _relu(z_grid)
    )
    completion = cfg.base_schedule_months + delay
    capex_delay_mult = 1.0 + cfg.capex_overrun_per_month_delay_fraction * delay

    # FX + construction commodities on capex; FX pass-through on revenue (stylised)
    fx_rev = np.exp(cfg.fx_revenue_elasticity * z_fx)
    fx_capex = np.exp(cfg.fx_capex_elasticity * z_fx)
    com_capex = np.exp(cfg.commodity_capex_elasticity * z_com)
    capex_layer = capex_delay_mult * fx_capex * com_capex

    # Power → utility prices + small pass-through to revenue (PPA / tariff indexation)
    utility_mult = np.exp(cfg.power_utility_elasticity * z_power)
    power_rev = np.exp(cfg.power_revenue_pass_through * z_power)

    # --- 4.2 Physical infrastructure (outage days + thermal stress)
    grid_days = cfg.baseline_grid_outage_days + cfg.grid_stress_to_outage_days * _sigmoid(z_grid)
    thermal_days = cfg.thermal_failure_days_per_unit * _relu(z_therm)
    raw_physical = grid_days + thermal_days
    physical_days = raw_physical * (1.0 - cfg.backup_mitigation_factor)

    # --- 4.4 Cyber (extra downtime + cost pressure)
    cyber_sev = _sigmoid(z_cyb - cfg.cyber_event_threshold)
    cyber_days = cfg.cyber_downtime_days * cyber_sev
    opex_cyber = 1.0 + cfg.cyber_recovery_cost_fraction_of_capex * cyber_sev

    total_downtime = physical_days + cyber_days
    availability = np.clip(1.0 - total_downtime / 365.0, 0.65, 1.0)
    sla_breach = (availability < cfg.sla_target_availability).astype(np.float64)

    # --- 4.3 Operational / contract (SLA + tenant concentration)
    avail_penalty = np.where(
        availability < cfg.sla_target_availability,
        1.0 - cfg.revenue_penalty_below_sla * (cfg.sla_target_availability - availability),
        1.0,
    )
    tenant_shock = _sigmoid(-z_rev / max(cfg.tenant_revenue_stress_scale, 1e-6))
    tenant_hit = 1.0 - cfg.tenant_concentration_top_share * cfg.tenant_default_probability_weight * tenant_shock
    revenue_ops = availability * avail_penalty * tenant_hit * power_rev * fx_rev

    opex_layer = opex_cyber

    return (
        FullStackAdjustment(
            revenue_mult=revenue_ops,
            capex_mult=capex_layer,
            opex_mult=opex_layer,
            utility_price_mult=utility_mult,
        ),
        LayerDiagnostics(
            schedule_delay_months=delay,
            critical_path_completion_months=completion,
            downtime_days=total_downtime,
            availability=availability,
            cyber_severity=cyber_sev,
            sla_breach=sla_breach,
        ),
    )


def milestone_completion_curve(completion_months: np.ndarray, horizons: list[float]) -> dict[str, float]:
    out: dict[str, float] = {}
    for h in horizons:
        key = f"by_month_{int(h)}"
        out[key] = float(np.mean(completion_months <= h))
    return out
