import numpy as np

from azraq_mc.cache import clear_shock_cache
from azraq_mc.engine import run_adhoc_asset_simulation
from azraq_mc.schemas import (
    AssetAssumptions,
    AssetFactorTransforms,
    FinancingAssumptions,
    ShockPackSpec,
)


def test_student_t_copula_runs():
    clear_shock_cache()
    asset = AssetAssumptions(
        asset_id="t1",
        assumption_set_id="as",
        horizon_years=8,
        base_revenue_annual=20.0,
        base_opex_annual=7.0,
        initial_capex=80.0,
        equity_fraction=0.4,
        tax_rate=0.0,
        financing=FinancingAssumptions(
            debt_principal=20.0,
            interest_rate_annual=0.055,
            loan_term_years=10,
            covenant_dscr=1.2,
        ),
        factor_transforms=AssetFactorTransforms(revenue_shock_scale=1.1, revenue_level_multiplier=0.98),
    )
    shock = ShockPackSpec(
        shockpack_id="tcop",
        seed=202,
        n_scenarios=3000,
        copula="student_t",
        t_degrees_freedom=6.0,
    )
    r = run_adhoc_asset_simulation(shock, asset)
    assert np.isfinite(r.metrics.dscr.p50)
    assert r.metadata.layer_versions is not None
