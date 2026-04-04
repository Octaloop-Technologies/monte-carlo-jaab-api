from __future__ import annotations

import json
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from azraq_mc.calibration_sources import materialize_shockpack_margins
from azraq_mc.schemas import (
    DynamicMarginsSpec,
    MarginCalibrationFileSource,
    RiskFactorMargins,
    ShockPackSpec,
    YahooFinanceVolBinding,
)


def test_materialize_no_dynamic_returns_unchanged():
    spec = ShockPackSpec(shockpack_id="s", seed=1, n_scenarios=100)
    out, trace = materialize_shockpack_margins(spec)
    assert out is spec
    assert trace is None


def test_file_excel_wide_overlay_merges_margins(tmp_path):
    p = tmp_path / "m.xlsx"
    df = pd.DataFrame(
        [
            {
                "revenue_log_sigma": 0.21,
                "opex_log_sigma": 0.04,
                "unrelated_column": 99,
            }
        ]
    )
    df.to_excel(p, index=False, engine="openpyxl")

    spec = ShockPackSpec(
        shockpack_id="s",
        seed=1,
        n_scenarios=100,
        margins=RiskFactorMargins(revenue_log_sigma=0.08),
        dynamic_margins=DynamicMarginsSpec(
            file=MarginCalibrationFileSource(path=str(p), mode="overlay"),
        ),
    )
    out, trace = materialize_shockpack_margins(spec)
    assert out.dynamic_margins is None
    assert out.margins.revenue_log_sigma == pytest.approx(0.21)
    assert out.margins.opex_log_sigma == pytest.approx(0.04)
    assert trace is not None
    assert trace["steps"][0]["source"] == "file"
    assert trace["steps"][0]["format"] == "excel"


def test_file_excel_key_value_columns(tmp_path):
    p = tmp_path / "m.xlsx"
    df = pd.DataFrame({"field": ["rate_shock_sigma", "capex_log_sigma"], "value": [0.012, 0.07]})
    df.to_excel(p, index=False, engine="openpyxl")

    spec = ShockPackSpec(
        shockpack_id="s",
        seed=1,
        n_scenarios=100,
        dynamic_margins=DynamicMarginsSpec(
            file=MarginCalibrationFileSource(path=str(p), mode="replace"),
        ),
    )
    out, trace = materialize_shockpack_margins(spec)
    assert out.margins.rate_shock_sigma == pytest.approx(0.012)
    assert out.margins.capex_log_sigma == pytest.approx(0.07)
    assert trace["steps"][0]["format"] == "excel"


def test_file_overlay_merges_margins(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"revenue_log_sigma": 0.2}), encoding="utf-8")
    spec = ShockPackSpec(
        shockpack_id="s",
        seed=1,
        n_scenarios=100,
        margins=RiskFactorMargins(revenue_log_sigma=0.08),
        dynamic_margins=DynamicMarginsSpec(
            file=MarginCalibrationFileSource(path=str(p), mode="overlay"),
        ),
    )
    out, trace = materialize_shockpack_margins(spec)
    assert out.dynamic_margins is None
    assert out.margins.revenue_log_sigma == pytest.approx(0.2)
    assert trace is not None
    assert trace["steps"][0]["source"] == "file"
    assert "resolved_margins" in trace


def test_yahoo_finance_binding_updates_target():
    spec = ShockPackSpec(
        shockpack_id="s",
        seed=1,
        n_scenarios=100,
        margins=RiskFactorMargins(revenue_log_sigma=0.01),
        dynamic_margins=DynamicMarginsSpec(
            yahoo_finance=[
                YahooFinanceVolBinding(symbol="TEST", period="5d", target="revenue_log_sigma", min_observations=5)
            ],
        ),
    )
    rng = np.random.default_rng(0)
    rets = rng.normal(0.001, 0.02, size=40)
    close = 100.0 * np.cumprod(1.0 + rets)
    df = pd.DataFrame({"Close": close.astype(np.float64)})

    class FakeTicker:
        def __init__(self, symbol: str) -> None:
            self.symbol = symbol

        def history(self, period: str):  # noqa: ARG002
            return df

    with patch("yfinance.Ticker", FakeTicker):
        out, trace = materialize_shockpack_margins(spec)

    assert out.dynamic_margins is None
    assert out.margins.revenue_log_sigma > 0.01
    assert trace is not None
    assert any(s.get("source") == "yahoo_finance" for s in trace["steps"])
