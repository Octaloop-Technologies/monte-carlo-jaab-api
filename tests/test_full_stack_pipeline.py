import numpy as np

from azraq_mc.cache import clear_shock_cache
from azraq_mc.engine import run_adhoc_asset_simulation
from azraq_mc.presets import FULL_STACK_FACTOR_ORDER, default_full_stack_correlation, make_full_stack_shockpack
from azraq_mc.schemas import AssetAssumptions, FinancingAssumptions, FullStackLayerConfig, ShockPackSpec


def test_correlation_is_psd():
    c = np.asarray(default_full_stack_correlation(), dtype=np.float64)
    assert c.shape == (12, 12)
    assert np.all(np.linalg.eigvalsh(c) > -1e-8)


def test_full_stack_simulation_has_layers():
    clear_shock_cache()
    shock = make_full_stack_shockpack("fs-pack", seed=55, n_scenarios=2000)
    assert shock.factor_order == FULL_STACK_FACTOR_ORDER
    asset = AssetAssumptions(
        asset_id="dc-stack",
        assumption_set_id="as-fs",
        horizon_years=12,
        base_revenue_annual=50e6,
        base_opex_annual=22e6,
        utility_opex_annual=8e6,
        initial_capex=320e6,
        equity_fraction=0.3,
        tax_rate=0.0,
        financing=FinancingAssumptions(
            debt_principal=100e6,
            interest_rate_annual=0.06,
            loan_term_years=15,
            covenant_dscr=1.2,
        ),
        full_stack=FullStackLayerConfig(enabled=True),
    )
    r = run_adhoc_asset_simulation(shock, asset)
    assert r.full_stack is not None
    assert r.full_stack.probability_sla_breach >= 0.0
    assert r.metrics.probability_of_default_proxy_dscr_lt_1 is not None
    assert "by_month_18" in r.full_stack.milestone_completion


def test_four_factor_still_works_without_full_stack():
    clear_shock_cache()
    shock = ShockPackSpec(shockpack_id="four", seed=3, n_scenarios=1500)
    asset = AssetAssumptions(
        asset_id="a",
        assumption_set_id="as",
        horizon_years=8,
        base_revenue_annual=11.0,
        base_opex_annual=5.0,
        initial_capex=45.0,
        equity_fraction=0.38,
        tax_rate=0.0,
        financing=FinancingAssumptions(
            debt_principal=20.0,
            interest_rate_annual=0.055,
            loan_term_years=10,
            covenant_dscr=1.2,
        ),
    )
    r = run_adhoc_asset_simulation(shock, asset)
    assert r.full_stack is None
    assert np.isfinite(r.metrics.dscr.p50)
