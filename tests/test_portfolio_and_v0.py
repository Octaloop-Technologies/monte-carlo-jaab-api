import numpy as np

from azraq_mc.cache import clear_shock_cache
from azraq_mc.engine import run_adhoc_asset_simulation
from azraq_mc.portfolio import run_portfolio_joint_simulation
from azraq_mc.schemas import AssetAssumptions, FinancingAssumptions, ShockPackSpec
from azraq_mc.snapshots import load_snapshot_typed, save_snapshot
from azraq_mc.v0 import run_v0_base_case


def _a1() -> AssetAssumptions:
    return AssetAssumptions(
        asset_id="a1",
        assumption_set_id="as-1",
        horizon_years=10,
        base_revenue_annual=10.0,
        base_opex_annual=4.0,
        initial_capex=50.0,
        equity_fraction=0.4,
        tax_rate=0.0,
        financing=FinancingAssumptions(
            debt_principal=30.0,
            interest_rate_annual=0.06,
            loan_term_years=10,
            covenant_dscr=1.2,
        ),
    )


def _a2() -> AssetAssumptions:
    return _a1().model_copy(
        update={"asset_id": "a2", "assumption_set_id": "as-2", "base_revenue_annual": 8.0}
    )


def test_portfolio_first_asset_matches_standalone():
    clear_shock_cache()
    shock = ShockPackSpec(shockpack_id="sp-p", seed=7, n_scenarios=4000)
    a1 = _a1()
    solo = run_adhoc_asset_simulation(shock, a1)
    joint = run_portfolio_joint_simulation(shock, "pf-1", "pas-1", [a1, _a2()])
    assert joint.per_asset[0].metrics.dscr.p50 == solo.metrics.dscr.p50
    assert joint.portfolio.n_assets == 2
    assert 0.0 <= joint.portfolio.probability_any_covenant_breach <= 1.0
    assert "2" in joint.portfolio.probability_at_least_k_breaches


def test_v0_base_npv():
    a = _a1()
    a.equity_discount_rate_for_npv = 0.08
    r = run_v0_base_case(a)
    assert r.base.dscr > 0
    assert r.metadata.execution_mode == "v0_base"
    assert r.base.npv_equity is not None
    assert np.isfinite(r.base.npv_equity)


def test_snapshot_roundtrip(tmp_path):
    clear_shock_cache()
    shock = ShockPackSpec(shockpack_id="sp-snap", seed=3, n_scenarios=1000)
    res = run_adhoc_asset_simulation(shock, _a1())
    path = save_snapshot(tmp_path, "asset_simulation", res, label="t1")
    loaded = load_snapshot_typed(path)
    assert loaded.metrics.dscr.p50 == res.metrics.dscr.p50


def test_attribution_shares_sum():
    clear_shock_cache()
    shock = ShockPackSpec(shockpack_id="sp-att", seed=11, n_scenarios=6000, sampling_method="monte_carlo")
    res = run_adhoc_asset_simulation(shock, _a1(), include_attribution=True)
    assert res.attribution is not None
    s = sum(res.attribution.share_of_abs_beta.values())
    assert abs(s - 1.0) < 1e-6
