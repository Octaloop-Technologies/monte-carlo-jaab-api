"""
Appendix J — stress / calibration data sources (reference catalogue).

The Monte Carlo core runs on parameterised distributions; this module documents
**where real-world series can come from** and how they typically map into this engine.

Integration paths:
- **yahoo** — `GET /v1/market/yfinance/{symbol}/…` + `ShockPackSpec.dynamic_margins.yahoo_finance`
- **ecb** — `GET /v1/market/ecb/eur-usd` (ECB daily reference rates XML)
- **http_json** — `dynamic_margins.http` pointing to **your** JSON (proxy IEA, NY Fed CSV→JSON, etc.)
- **file** — `dynamic_margins.file` with margin patch JSON
- **manual** — analyst pastes resolved numbers after downloading from the official portal
"""
from __future__ import annotations

from typing import Any, Literal

IntegrationPath = Literal["yahoo", "ecb", "http_json", "file", "manual"]
ReleaseTier = Literal["primary", "secondary"]


def stress_data_catalog() -> list[dict[str, Any]]:
    """Ordered catalogue rows aligned with product Appendix J."""
    return [
        _row(
            "global_shipping_index",
            "Construction & Supply Chain",
            "Global Shipping Index",
            "Equipment delivery risk",
            "Construction delay",
            "Shipping cost +40%",
            "secondary",
            None,
            ("baltic dry / container indices vary by vendor; often manual file or "
             "proprietary feed → use `dynamic_margins.file` / `http_json` hosted JSON."),
            (),
        ),
        _row(
            "transformer_lead_time",
            "Construction & Supply Chain",
            "Transformer Lead Time Index",
            "Critical infrastructure bottleneck",
            "Commissioning delay",
            "Lead time +6 months",
            "secondary",
            None,
            ("Survey or OEM data — not a single public ticker; **manual** or **file**."),
            (),
        ),
        _row(
            "labour_cost_index",
            "Construction & Supply Chain",
            "Labour Cost Index",
            "Skilled engineer availability",
            "Capex + Opex inflation",
            "+10% labour cost",
            "secondary",
            None,
            ("National stats or construction wage indices — **file** / **http_json**."),
            (),
        ),
        _row(
            "ai_investment_index",
            "Demand & Tech Cycle",
            "AI Investment Index",
            "AI workload demand growth",
            "Expansion acceleration",
            "AI funding -30%",
            "secondary",
            None,
            ("Composite indices from research vendors — **manual** / **file**."),
            (),
        ),
        _row(
            "hyperscaler_capex_trend",
            "Demand & Tech Cycle",
            "Hyperscaler Capex Trend",
            "Leading demand indicator",
            "Occupancy slowdown risk",
            "Capex -20% YoY",
            "primary",
            None,
            ("Filings / segment data — **manual** or hosted JSON (**http_json**). "
             "Optional equity proxies e.g. cloud-heavy ETF via **yahoo** for coarse vol."),
            (),
        ),
        _row(
            "datacentre_vacancy_rate",
            "Demand & Tech Cycle",
            "Data Centre Vacancy Rate",
            "Pricing power indicator",
            "Revenue compression",
            "Vacancy +5%",
            "primary",
            None,
            ("Broker / CBRE-style series — **manual** / **file**; map to revenue shocks."),
            (),
        ),
        _row(
            "brent_oil",
            "Energy & Commodities",
            "Brent Oil Price",
            "Impacts diesel backup, transport, logistics",
            "Opex + construction cost",
            "+30% oil shock",
            "secondary",
            None,
            "ICE Brent crude is often proxied on Yahoo as **BZ=F** (verify with your market data policy).",
            ("yahoo",),
        ),
        _row(
            "coal_price",
            "Energy & Commodities",
            "Coal Price",
            "Relevant in coal-heavy grids",
            "Electricity tariff increase",
            "+25% coal shock",
            "secondary",
            None,
            ("Exchange-traded coal / ETF proxies exist (**yahoo** tickers vary); else **manual**."),
            ("yahoo",),
        ),
        _row(
            "aluminium_price",
            "Energy & Commodities",
            "Aluminium Price",
            "Cable & cooling equipment cost",
            "Capex shock",
            "+15% aluminium",
            "secondary",
            None,
            "LME/aluminium futures proxies sometimes quoted as **ALI=F** on Yahoo (verify).",
            ("yahoo",),
        ),
        _row(
            "natural_gas_ttf_henry_hub",
            "Energy & Commodities",
            "Natural Gas Price (TTF / Henry Hub)",
            "Drives wholesale electricity pricing",
            "Power cost volatility",
            "+40% gas price shock",
            "primary",
            None,
            ("**Henry Hub** often **NG=F** on Yahoo; **TTF** may need ICE / Refinitiv → **manual** or **http_json**."),
            ("yahoo",),
        ),
        _row(
            "copper_price",
            "Energy & Commodities",
            "Copper Price",
            "Electrical infrastructure cost driver",
            "Capex overrun risk",
            "+20% copper price",
            "primary",
            "https://finance.yahoo.com/quote/HG%3DF/history/",
            ("High-Grade Copper COMEX continuous futures: **HG=F** on Yahoo.",),
            ("yahoo",),
        ),
        _row(
            "steel_price",
            "Energy & Commodities",
            "Steel Price",
            "Structural construction cost",
            "EPC cost inflation",
            "+15% steel",
            "primary",
            None,
            ("Hot-rolled coil / rebar系列 differ; **file** / **http_json** or steel ETF proxy (**SLX** etc.) **yahoo**.",
            ),
            ("yahoo", "manual"),
        ),
        _row(
            "carbon_price_eu_ets",
            "Energy & Commodities",
            "Carbon Price (EU ETS / regional)",
            "Impacts fossil-heavy grids",
            "Electricity cost increase",
            "+50% carbon price",
            "primary",
            None,
            ("EU ETS from ICE/Refinitiv — **manual** / hosted **http_json**; map to **power_price** / opex."),
            (),
        ),
        _row(
            "grid_congestion_index",
            "Energy Markets",
            "Grid Congestion Index",
            "Curtailment & downtime risk",
            "Revenue loss / SLA breach",
            "5% uptime reduction",
            "secondary",
            None,
            ("ISO/RTO datasets — **manual** / **file**; ties to **grid_interconnection** in full_stack."),
            (),
        ),
        _row(
            "renewable_ppa_price",
            "Energy Markets",
            "Renewable PPA Price",
            "Long-term hedging exposure",
            "Cost renegotiation risk",
            "+20% PPA price",
            "secondary",
            None,
            ("PPA benchmarks from brokers — **manual** / **file**.",),
            (),
        ),
        _row(
            "wholesale_electricity_price",
            "Energy Markets",
            "Wholesale Electricity Price",
            "Core OPEX driver",
            "Direct NOI impact",
            "+50% electricity price",
            "primary",
            "https://www.iea.org/data-and-statistics/data-product/global-energy-and-climate-model-key-input-data",
            ("IEA portal: typically **manual** download or your **http_json** proxy; regional power may use **yahoo** power/utility proxies.",
            ),
            ("manual", "http_json"),
        ),
        _row(
            "em_fx_index",
            "FX & Cross-Border",
            "Emerging Market FX Index",
            "Emerging market exposure",
            "Revenue devaluation risk",
            "15% EM FX drop",
            "secondary",
            None,
            ("MSCI / JPM EMCI style — **manual**; coarse **yahoo** proxy e.g. **EEM** realised vol for `fx` factor.",
            ),
            ("yahoo", "manual"),
        ),
        _row(
            "usd_eur_fx",
            "FX & Cross-Border",
            "USD/EUR Exchange Rate",
            "Revenue vs debt mismatch",
            "FX translation loss",
            "10% currency move",
            "primary",
            "https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html",
            ("ECB daily reference XML — **GET /v1/market/ecb/eur-usd** in this API; or host EURUSD series as **http_json** for margins.",
            ),
            ("ecb", "http_json", "manual"),
        ),
        _row(
            "sofr",
            "Interest & Credit Markets",
            "SOFR",
            "Floating debt exposure",
            "Interest cost increase",
            "+bps rate shock",
            "primary",
            "https://www.newyorkfed.org/markets/reference-rates/sofr",
            ("NY Fed publishes SOFR averages; ingest via your **http_json** bridge or **file**; map to `rate_shock_sigma` / macro ladder.",
            ),
            ("http_json", "file", "manual"),
        ),
        _row(
            "sonia",
            "Interest & Credit Markets",
            "SONIA",
            "UK floating-rate exposure",
            "Interest cost increase",
            "+bps rate shock",
            "primary",
            "https://www.bankofengland.co.uk/boeapps/database/",
            ("BoE time series database — **manual** / **http_json** after ETL; same margin mapping as SOFR.",
            ),
            ("http_json", "file", "manual"),
        ),
        _row(
            "govt_10y_yield",
            "Interest & Credit Markets",
            "10Y Government Yield",
            "Refinancing benchmark",
            "Exit valuation & refinancing cost",
            "+150bps yield shift",
            "primary",
            None,
            ("Proxy: US **^TNX** on Yahoo for coarse history/vol; sovereign-specific series via **file**/**http_json**.",
            ),
            ("yahoo", "file", "http_json"),
        ),
        _row(
            "credit_spread_index",
            "Interest & Credit Markets",
            "Credit Spread Index",
            "Debt market stress",
            "Refinancing cost increase",
            "+150bps spread widening",
            "primary",
            None,
            ("IG/HY indices from Fed FRED / ICE — **http_json** proxy or **file**; add to rate margin / spread overlay.",
            ),
            ("http_json", "file", "manual"),
        ),
        _row(
            "inflation_cpi",
            "Interest & Credit Markets",
            "Inflation (CPI)",
            "Opex & wage escalation",
            "Cost inflation",
            "+3% CPI shock",
            "primary",
            None,
            ("National stats — **file**/**http_json**; engine also supports **inflation_process** on `ShockPackSpec` for pass-through.",
            ),
            ("file", "http_json", "manual"),
        ),
        _row(
            "vix",
            "Systemic Financial Stress",
            "VIX Index",
            "Risk-off environment proxy",
            "Financing cost spike",
            "VIX > 40",
            "secondary",
            None,
            "Yahoo **^VIX** for history; often scaled into `rate_shock_sigma` or narrative stress overlay.",
            ("yahoo",),
        ),
        _row(
            "bank_cds",
            "Systemic Financial Stress",
            "Bank CDS Spreads",
            "Banking system health",
            "Debt availability risk",
            "+200bps CDS widening",
            "secondary",
            None,
            ("Markit / ICE CDS — proprietary; **manual**/**file**.",),
            (),
        ),
        _row(
            "infra_fundraising_volume",
            "Systemic Financial Stress",
            "Infrastructure Fundraising Volume",
            "Capital availability",
            "Equity cost increase",
            "Fundraising -30%",
            "secondary",
            None,
            ("Preqin / industry reports — **manual**/**file**.",),
            (),
        ),
    ]


def _row(
    source_id: str,
    category: str,
    macro_metric: str,
    why_datacentre: str,
    transmission_channel: str,
    example_stress: str,
    tier: ReleaseTier,
    source_url: str | None,
    engine_integration_note: str,
    integration_paths: tuple[IntegrationPath, ...],
    *,
    suggested_yahoo: str | None = None,
) -> dict[str, Any]:
    if suggested_yahoo is None:
        if "HG=F" in engine_integration_note:
            suggested_yahoo = "HG=F"
        elif source_id == "brent_oil":
            suggested_yahoo = "BZ=F"
        elif source_id == "natural_gas_ttf_henry_hub":
            suggested_yahoo = "NG=F"
        elif source_id == "vix":
            suggested_yahoo = "^VIX"
        elif source_id == "govt_10y_yield":
            suggested_yahoo = "^TNX"
        elif source_id == "em_fx_index":
            suggested_yahoo = "EEM"
        elif source_id == "aluminium_price":
            suggested_yahoo = "ALI=F"
    return {
        "id": source_id,
        "category": category,
        "macro_metric": macro_metric,
        "why_it_matters_for_data_centres": why_datacentre,
        "transmission_channel": transmission_channel,
        "example_stress_scenario": example_stress,
        "release_tier": tier,
        "official_or_example_source_url": source_url,
        "engine_integration_note": engine_integration_note,
        "integration_paths": list(integration_paths),
        "suggested_yahoo_finance_symbol": suggested_yahoo,
        "typical_engine_hooks": {
            "margin_targets": [
                "revenue_log_sigma",
                "capex_log_sigma",
                "opex_log_sigma",
                "rate_shock_sigma",
            ],
            "full_stack_factor_hints": [
                "fx",
                "power_price",
                "commodity_construction",
                "revenue",
                "rate",
            ],
            "spec_features": ["dynamic_margins.yahoo_finance", "dynamic_margins.http", "dynamic_margins.file", "macro_term_structure", "inflation_process"],
        },
    }


def catalog_integration_overview() -> dict[str, Any]:
    return {
        "yahoo_finance": (
            "Use GET /v1/market/yfinance/{symbol}/history|returns for inspection; "
            "use ShockPackSpec.dynamic_margins.yahoo_finance[] to map annualised vol into margin sigmas."
        ),
        "ecb_eur_usd": (
            "Use GET /v1/market/ecb/eur-usd for the ECB’s published daily USD rate against EUR."
        ),
        "http_json_overlay": (
            "Host or proxy any official series as JSON and point dynamic_margins.http.url at it "
            "(body must match margin patch shape documented in docs/API.md)."
        ),
        "margin_file": "Use dynamic_margins.file to load a JSON margin patch from a controlled path.",
        "manual": "Analyst resolves numbers offline and pastes margins into ShockPackSpec or registers a shock pack in the catalogue.",
        "engine_note": (
            "No live vendor feed is required to run Monte Carlo: external data only informs parameters before simulate."
        ),
    }
