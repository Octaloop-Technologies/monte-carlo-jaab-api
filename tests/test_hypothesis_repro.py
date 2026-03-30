from hypothesis import given, settings
from hypothesis import strategies as st

from azraq_mc.cache import clear_shock_cache
from azraq_mc.engine import run_adhoc_asset_simulation
from azraq_mc.schemas import AssetAssumptions, FinancingAssumptions, ShockPackSpec


def _asset() -> AssetAssumptions:
    return AssetAssumptions(
        asset_id="hyp-asset",
        assumption_set_id="hyp-as",
        horizon_years=5,
        base_revenue_annual=12.0,
        base_opex_annual=5.0,
        utility_opex_annual=2.0,
        initial_capex=40.0,
        equity_fraction=0.35,
        tax_rate=0.0,
        financing=FinancingAssumptions(
            debt_principal=10.0,
            interest_rate_annual=0.05,
            loan_term_years=8,
            covenant_dscr=1.15,
        ),
    )


@settings(deadline=None, max_examples=15)
@given(
    seed=st.integers(min_value=0, max_value=2**31 - 1),
    n=st.integers(min_value=500, max_value=1500),
)
def test_reproducible_monte_carlo(seed: int, n: int):
    clear_shock_cache()
    shock = ShockPackSpec(shockpack_id="hyp-pack", seed=seed, n_scenarios=n)
    asset = _asset()
    a = run_adhoc_asset_simulation(shock, asset)
    clear_shock_cache()
    b = run_adhoc_asset_simulation(shock, asset)
    assert a.metrics.dscr.p50 == b.metrics.dscr.p50
    assert a.metrics.dscr.p10 == b.metrics.dscr.p10
    assert a.metrics.covenant_breach_probability == b.metrics.covenant_breach_probability
