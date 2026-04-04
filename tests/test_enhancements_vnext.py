"""Tests for time paths, layered Z-cache, CPM, and catalogue."""
from __future__ import annotations

import numpy as np

from azraq_mc.cache import clear_shock_cache, get_or_build_z_core, z_core_fingerprint
from azraq_mc.cpm import critical_path_months_batch
from azraq_mc.schemas import (
    AssetAssumptions,
    CpmTaskShockLink,
    CpmTaskSpec,
    FinancingAssumptions,
    FullStackLayerConfig,
    RiskFactorMargins,
    ShockPackSpec,
    TimeGridSpec,
)
from azraq_mc.shockpack import build_shock_array
from azraq_mc.shockpack_catalog import register_spec


def test_time_grid_3d_z_shape():
    spec = ShockPackSpec(
        shockpack_id="tg",
        seed=7,
        n_scenarios=500,
        time_grid=TimeGridSpec(n_periods=4, dynamics="iid"),
    )
    arr = build_shock_array(spec)
    z = np.asarray(arr.z)
    assert z.shape == (500, 4, 4)


def test_z_cache_ignores_margins():
    clear_shock_cache()
    m0 = RiskFactorMargins(revenue_log_sigma=0.05)
    a = ShockPackSpec(shockpack_id="z1", seed=1, n_scenarios=200, margins=m0)
    b = a.model_copy(update={"margins": m0.model_copy(update={"revenue_log_sigma": 0.20})})
    assert z_core_fingerprint(a) == z_core_fingerprint(b)
    za = get_or_build_z_core(a)
    zb = get_or_build_z_core(b)
    assert za.shape == zb.shape
    assert np.allclose(za, zb)


def test_cpm_critical_path_longer_than_parallel():
    # A -> B -> C chain vs short side task
    tasks = (
        CpmTaskSpec(task_id="A", duration_base_months=6.0),
        CpmTaskSpec(task_id="B", duration_base_months=4.0, predecessor_ids=("A",)),
        CpmTaskSpec(
            task_id="C",
            duration_base_months=3.0,
            predecessor_ids=("B",),
            shock_links=(CpmTaskShockLink(factor_id="permit_regulatory", months_per_positive_z=2.0),),
        ),
    )
    n, k = 50, 12
    z = np.zeros((n, k), dtype=np.float64)
    fo = (
        "revenue",
        "capex",
        "opex",
        "rate",
        "fx",
        "power_price",
        "commodity_construction",
        "permit_regulatory",
        "weather",
        "grid_interconnection",
        "thermal_cooling",
        "cyber",
    )
    z[:, fo.index("permit_regulatory")] = 1.0
    cp = critical_path_months_batch(tasks, z, fo)
    assert np.all(cp > 13.0 + 1e-6)


def test_catalog_register_roundtrip(tmp_path):
    spec = ShockPackSpec(shockpack_id="cat-1", seed=2, n_scenarios=300)
    eid = register_spec(spec, db_path=tmp_path / "cat.sqlite3")
    from azraq_mc.shockpack_catalog import load_entry

    row = load_entry(eid, db_path=tmp_path / "cat.sqlite3")
    assert row["shockpack_id"] == "cat-1"


def test_full_stack_cpm_overrides_aggregate_delay():
    from azraq_mc.engine import run_adhoc_asset_simulation
    from azraq_mc.presets import make_full_stack_shockpack

    clear_shock_cache()
    shock = make_full_stack_shockpack("cpm-pack", seed=12, n_scenarios=800)
    tasks = (
        CpmTaskSpec(task_id="perm", duration_base_months=8.0),
        CpmTaskSpec(task_id="build", duration_base_months=10.0, predecessor_ids=("perm",)),
    )
    fs = FullStackLayerConfig(
        enabled=True,
        base_schedule_months=12.0,
        cpm_tasks=tasks,
        permit_delay_sensitivity_months=99.0,
    )
    asset = AssetAssumptions(
        asset_id="x",
        assumption_set_id="y",
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
        full_stack=fs,
    )
    r = run_adhoc_asset_simulation(shock, asset, include_attribution=True)
    assert r.full_stack is not None
    assert r.metadata.compute_time_ms is not None
    assert r.attribution is not None
    assert r.attribution.bucket_shares
