from azraq_mc.engine import run_adhoc_asset_simulation
from azraq_mc.schemas import AssetAssumptions, FinancingAssumptions, ShockPackSpec


def _fixture_asset() -> AssetAssumptions:
    return AssetAssumptions(
        asset_id="test-asset",
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


def _fixture_shock() -> ShockPackSpec:
    return ShockPackSpec(
        shockpack_id="sp-test",
        seed=123,
        n_scenarios=5000,
    )


def test_same_seed_same_metrics():
    a, s = _fixture_asset(), _fixture_shock()
    r1 = run_adhoc_asset_simulation(s, a)
    r2 = run_adhoc_asset_simulation(s, a)
    assert r1.metrics.covenant_breach_probability == r2.metrics.covenant_breach_probability
    assert r1.metrics.dscr.p50 == r2.metrics.dscr.p50
    assert r1.metrics.irr_annual is not None and r2.metrics.irr_annual is not None
    assert r1.metrics.irr_annual.p50 == r2.metrics.irr_annual.p50


def test_different_seed_changes_metrics_slightly():
    a = _fixture_asset()
    s1 = ShockPackSpec(shockpack_id="sp-a", seed=1, n_scenarios=8000)
    s2 = ShockPackSpec(shockpack_id="sp-b", seed=999, n_scenarios=8000)
    r1 = run_adhoc_asset_simulation(s1, a)
    r2 = run_adhoc_asset_simulation(s2, a)
    assert r1.metrics.dscr.mean != r2.metrics.dscr.mean or r1.metrics.dscr.p95 != r2.metrics.dscr.p95
