"""Macro curves, waterfall, CPM resources, catalogue promotion, advanced attribution."""
from __future__ import annotations

import numpy as np

from azraq_mc.cpm_resource import critical_path_months_with_resources
from azraq_mc.engine import run_adhoc_asset_simulation
from azraq_mc.macro_curves import macro_effective_vol_scalar, rate_additive_shock
from azraq_mc.schemas import (
    AssetAssumptions,
    CpmResourcePool,
    CpmTaskSpec,
    FinancingAssumptions,
    InflationProcessSpec,
    MacroTermStructureSpec,
    RiskFactorMargins,
    ShockPackSpec,
    WaterfallAssumptions,
)
from azraq_mc.shockpack_catalog import load_entry, promote_entry, register_spec


def test_macro_effective_vol_scalar_amplifies():
    spec = MacroTermStructureSpec(
        tenor_years=(1.0, 5.0),
        loadings=(0.5, 0.5),
        parallel_vol_multipliers=(1.5, 2.0),
    )
    assert macro_effective_vol_scalar(spec) > 1.0


def test_rate_additive_shock_matches_scalar():
    m = RiskFactorMargins(rate_shock_sigma=0.01)
    macro = MacroTermStructureSpec(
        tenor_years=(1.0, 2.0),
        loadings=(0.5, 0.5),
        parallel_vol_multipliers=None,
    )
    z = np.array([1.0, -0.5, 0.0])
    r = rate_additive_shock(z, m, macro)
    assert r.shape == z.shape
    assert np.allclose(r, m.rate_shock_sigma * z * macro_effective_vol_scalar(macro))


def test_waterfall_reduces_levered_cf():
    base = ShockPackSpec(shockpack_id="wf", seed=3, n_scenarios=400)
    asset_base = AssetAssumptions(
        asset_id="a",
        assumption_set_id="s",
        horizon_years=10,
        base_revenue_annual=20e6,
        base_opex_annual=9e6,
        initial_capex=80e6,
        equity_fraction=0.35,
        tax_rate=0.21,
        financing=FinancingAssumptions(
            debt_principal=40e6,
            interest_rate_annual=0.06,
            loan_term_years=15,
            covenant_dscr=1.2,
        ),
    )
    wf = WaterfallAssumptions(
        enabled=True,
        dsra_months_of_debt_service=6.0,
        lc_commitment_fee_annual_pct=0.002,
    )
    asset_wf = asset_base.model_copy(update={"waterfall": wf})
    r0 = run_adhoc_asset_simulation(base, asset_base)
    r1 = run_adhoc_asset_simulation(base, asset_wf)
    assert r1.metrics.levered_cf is not None and r0.metrics.levered_cf is not None
    assert r1.metrics.levered_cf.mean < r0.metrics.levered_cf.mean
    assert r1.extensions and "waterfall_dsra_mean_annual" in r1.extensions


def test_inflation_enabled_changes_opex_channel():
    sp = ShockPackSpec(
        shockpack_id="inf",
        seed=9,
        n_scenarios=300,
        inflation_process=InflationProcessSpec(enabled=True, log_sigma=0.05, opex_beta=1.0),
    )
    sp0 = sp.model_copy(update={"inflation_process": InflationProcessSpec(enabled=False)})
    asset = AssetAssumptions(
        asset_id="a",
        assumption_set_id="s",
        horizon_years=8,
        base_revenue_annual=15e6,
        base_opex_annual=7e6,
        initial_capex=60e6,
        equity_fraction=0.4,
        tax_rate=0.0,
        financing=FinancingAssumptions(
            debt_principal=30e6,
            interest_rate_annual=0.055,
            loan_term_years=12,
            covenant_dscr=1.15,
        ),
    )
    r_on = run_adhoc_asset_simulation(sp, asset)
    r_off = run_adhoc_asset_simulation(sp0, asset)
    assert r_on.metrics.ebitda is not None and r_off.metrics.ebitda is not None
    assert r_on.metrics.ebitda.std != r_off.metrics.ebitda.std


def test_cpm_resource_stretches_vs_plain_cpm():
    from azraq_mc.cpm import critical_path_months_batch
    from azraq_mc.presets import FULL_STACK_FACTOR_ORDER

    tasks = (
        CpmTaskSpec(task_id="a", duration_base_months=5.0, resource_id="crew", resource_units=3.0),
        CpmTaskSpec(
            task_id="b",
            duration_base_months=5.0,
            predecessor_ids=("a",),
            resource_id="crew",
            resource_units=3.0,
        ),
    )
    pools = (CpmResourcePool(resource_id="crew", capacity_units=4.0, calendar_efficiency=1.0),)
    n = 30
    z = np.zeros((n, len(FULL_STACK_FACTOR_ORDER)))
    plain = critical_path_months_batch(tasks, z, FULL_STACK_FACTOR_ORDER)
    rsrc = critical_path_months_with_resources(tasks, pools, z, FULL_STACK_FACTOR_ORDER)
    assert np.all(rsrc >= plain - 1e-9)


def test_catalog_promote_and_hash(tmp_path, monkeypatch):
    monkeypatch.setenv("AZRAQ_CATALOG_PROMOTER_ROLES", "")
    spec = ShockPackSpec(shockpack_id="promo", seed=1, n_scenarios=200)
    db = tmp_path / "c.sqlite3"
    eid = register_spec(spec, db_path=db, tenant_id="t1", promotion_tier="dev")
    row = load_entry(eid, db_path=db)
    assert row["promotion_tier"] == "dev"
    assert row["content_sha256"] and len(row["content_sha256"]) == 64
    promote_entry(eid, "prod", db_path=db)
    row2 = load_entry(eid, db_path=db)
    assert row2["promotion_tier"] == "prod"


def test_advanced_attribution_fields():
    from azraq_mc.presets import make_full_stack_shockpack

    shock = make_full_stack_shockpack("adv", seed=11, n_scenarios=600)
    asset = AssetAssumptions(
        asset_id="a",
        assumption_set_id="s",
        horizon_years=10,
        base_revenue_annual=20e6,
        base_opex_annual=9e6,
        initial_capex=100e6,
        equity_fraction=0.4,
        tax_rate=0.0,
        financing=FinancingAssumptions(
            debt_principal=40e6,
            interest_rate_annual=0.06,
            loan_term_years=12,
            covenant_dscr=1.2,
        ),
    )
    r = run_adhoc_asset_simulation(
        shock, asset, include_attribution=True, include_advanced_attribution=True
    )
    assert r.attribution is not None
    assert r.attribution.euler_risk_contributions
    assert r.attribution.shapley_risk_contributions
