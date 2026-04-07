# Presentation walkthrough — API calls (basic → Yahoo → Monte Carlo)

Use this during a live demo: start simple, then market data, then calibration, then full simulation.

### Example responses in this document

The JSON blocks under **Example response** are **realistic shapes** from the codebase. Where noted, numeric examples were produced by running the engine locally (same inputs as the walkthrough). **Your live calls will differ slightly**: `run_id`, timestamps, Yahoo prices, ECB dates, and calibrated `capex_log_sigma` change over time. **Error responses** are noted per endpoint (401 if `AZRAQ_API_KEY` is set but the header is missing, 404 for bad Yahoo symbols, etc.).

---

## Before you start

**1. Install and run the API** (from the repo root):

```bash
pip install -r requirements.txt
python -m uvicorn azraq_mc.api:app --reload --host 127.0.0.1 --port 8000
```

**2. Open interactive docs:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

**3. Optional API key:** If `AZRAQ_API_KEY` is set in `.env`, add this header to every request **except** `GET /health`:

```text
X-API-Key: <same value as AZRAQ_API_KEY>
```

**4. Shell note (Windows):** Examples below use `curl`. In PowerShell, use `curl.exe` (not the `curl` alias) so flags match, or run from Git Bash.

**5. Base URL** (used in all steps):

```text
http://127.0.0.1:8000
```

---

## Step 1 — Health check (simplest call)

Confirms the server is running. **No API key required** even when other routes require `X-API-Key`.

**Request:**

```bash
curl -s http://127.0.0.1:8000/health
```

**Example response** (200):

```json
{
  "status": "ok",
  "response_help": {
    "what_you_sent": "Nothing—this is a quick ping.",
    "what_you_received": "A short JSON saying the service answered (for example status \"ok\").",
    "findings_and_next_steps": "If this fails, the app is not reachable—fix hosting before trying heavier calls. This ping does **not** prove a database or simulation works."
  }
}
```

---

## Step 2 — Stress data catalogue (optional narrative)

Shows how external sources (Yahoo copper, ECB, files, HTTP) relate to calibration — good “Appendix J” slide material.

**Request:**

```bash
curl -s http://127.0.0.1:8000/v1/calibration/stress-data-catalog
```

(Add `-H "X-API-Key: …"` when `AZRAQ_API_KEY` is set.)

**Example response** (200) — **abridged** (real `sources` has many rows; one row shown — **copper** — as returned today):

```json
{
  "sources": [
    {
      "id": "copper_price",
      "category": "Energy & Commodities",
      "macro_metric": "Copper Price",
      "why_it_matters_for_data_centres": "Electrical infrastructure cost driver",
      "transmission_channel": "Capex overrun risk",
      "example_stress_scenario": "+20% copper price",
      "release_tier": "primary",
      "official_or_example_source_url": "https://finance.yahoo.com/quote/HG%3DF/history/",
      "engine_integration_note": [
        "High-Grade Copper COMEX continuous futures: **HG=F** on Yahoo."
      ],
      "integration_paths": ["yahoo"],
      "suggested_yahoo_finance_symbol": null,
      "typical_engine_hooks": {
        "margin_targets": [
          "revenue_log_sigma",
          "capex_log_sigma",
          "opex_log_sigma",
          "rate_shock_sigma"
        ],
        "full_stack_factor_hints": ["fx", "power_price", "commodity_construction", "revenue", "rate"],
        "spec_features": [
          "dynamic_margins.yahoo_finance",
          "dynamic_margins.http",
          "dynamic_margins.file",
          "macro_term_structure",
          "inflation_process"
        ]
      }
    }
  ],
  "integration_overview": {
    "yahoo_finance": "Use GET /v1/market/yfinance/{symbol}/history|returns for inspection; use ShockPackSpec.dynamic_margins.yahoo_finance[] to map annualised vol into margin sigmas.",
    "ecb_eur_usd": "Use GET /v1/market/ecb/eur-usd for the ECB’s published daily USD rate against EUR.",
    "http_json_overlay": "Host or proxy any official series as JSON and point dynamic_margins.http.url at it (body must match margin / patch shape in API.md).",
    "margin_file": "Use dynamic_margins.file to load a JSON margin patch from a controlled path.",
    "manual": "Analyst resolves numbers offline and pastes margins into ShockPackSpec or registers a shock pack in the catalogue.",
    "engine_note": "No live vendor feed is required to run Monte Carlo: external data only informs parameters before simulate."
  },
  "response_help": {
    "what_you_sent": "…",
    "what_you_received": "…",
    "findings_and_next_steps": "…"
  }
}
```

**Other codes:** `401` with `{"detail":"Invalid or missing X-API-Key"}` if the key env is set and you omit the header.

---

## Step 3 — Yahoo Finance: copper price history (exploratory)

Raw OHLCV from Yahoo. **Requires `yfinance`** (in `requirements.txt`). Symbol for COMEX high-grade copper: **`HG=F`**.

**Request:**

```bash
curl -s "http://127.0.0.1:8000/v1/market/yfinance/HG=F/history?period=1y"
```

**Example response** (200) — **truncated** `data` (many rows in production):

```json
{
  "symbol": "HG=F",
  "period": "1y",
  "data": [
    {
      "Date": "2025-04-07",
      "Open": 4.9,
      "High": 5.01,
      "Low": 4.88,
      "Close": 4.97,
      "Volume": 12345,
      "Dividends": 0.0,
      "Stock Splits": 0.0
    }
  ],
  "response_help": {
    "what_you_sent": "…",
    "what_you_received": "…",
    "findings_and_next_steps": "…"
  }
}
```

**Other codes:** `404` — no series for symbol/period; `501` — `yfinance` not installed.

---

## Step 4 — Yahoo Finance: daily returns (sanity check)

Simple close-to-close returns — easier to reason about volatility than raw prices.

**Request:**

```bash
curl -s "http://127.0.0.1:8000/v1/market/yfinance/HG=F/returns?period=1y"
```

**Example response** (200) — **truncated** `returns`:

```json
{
  "symbol": "HG=F",
  "period": "1y",
  "returns": [
    { "date": "2025-04-08", "return": 0.00241 },
    { "date": "2025-04-09", "return": -0.0103 }
  ],
  "n": 252,
  "response_help": {
    "what_you_sent": "…",
    "what_you_received": "…",
    "findings_and_next_steps": "…"
  }
}
```

The Monte Carlo Yahoo calibration uses **log** returns and **sqrt(252)** annualisation; this endpoint is for human inspection.

---

## Step 5 — ECB EUR/USD (optional; not Yahoo)

Official spot from ECB XML — illustrates **non-Yahoo** market helper.

**Request:**

```bash
curl -s http://127.0.0.1:8000/v1/market/ecb/eur-usd
```

**Example response** (200):

```json
{
  "source": "ecb",
  "source_url": "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml",
  "rate_date": "2026-04-02",
  "quote": "EUR/USD",
  "one_eur_in_usd": 1.1525,
  "response_help": {
    "what_you_sent": "…",
    "what_you_received": "…",
    "findings_and_next_steps": "…"
  }
}
```

**Other codes:** `502` if ECB XML cannot be fetched or parsed.

---

## Step 6 — Deterministic base case (no randomness)

One scenario, spreadsheet-style baseline — **not** Monte Carlo. Body **is** the asset object (not wrapped).

**Request:**

```bash
curl -s -X POST http://127.0.0.1:8000/v1/simulate/v0/base-case \
  -H "Content-Type: application/json" \
  -d "{\"asset_id\":\"demo-asset-1\",\"assumption_set_id\":\"demo-as-1\",\"horizon_years\":8,\"base_revenue_annual\":12000000,\"base_opex_annual\":5000000,\"initial_capex\":80000000,\"equity_fraction\":0.35,\"tax_rate\":0.0,\"financing\":{\"debt_principal\":40000000,\"interest_rate_annual\":0.055,\"loan_term_years\":12,\"covenant_dscr\":1.2}}"
```

**Example response** (200) — `run_id` / `created_at_utc` will differ each call:

```json
{
  "metadata": {
    "run_id": "bf06c66c-04e5-40aa-a58d-83f39d9edd37",
    "shockpack_id": "v0-deterministic",
    "assumption_set_id": "demo-as-1",
    "asset_id": "demo-asset-1",
    "model_version": "azraq-mc-v0",
    "seed": 0,
    "n_scenarios": 1,
    "sampling_method": "monte_carlo",
    "created_at_utc": "2026-04-06T21:16:23.118169Z",
    "execution_mode": "v0_base",
    "margin_calibration_trace": null,
    "compute_time_ms": null,
    "performance_profile": null
  },
  "base": {
    "dscr": 1.160185095022102,
    "irr_annual": -0.2216095508039616,
    "annual_revenue": 12000000.0,
    "ebitda": 7000000.0,
    "debt_service": 6033520.02196395,
    "initial_equity": 28000000.0,
    "utility_opex_exposure": 0.0,
    "revenue_multiplier": 1.0,
    "capex_multiplier": 1.0,
    "opex_multiplier": 1.0,
    "effective_interest_rate": 0.055,
    "npv_equity": null,
    "enterprise_value": null
  },
  "response_help": {
    "what_you_sent": "You sent one project's finances only—no random stress test.",
    "what_you_received": "You get a single set of figures: one debt-cover ratio, one return figure …",
    "findings_and_next_steps": "Use this to check that the model matches a spreadsheet baseline …",
    "glossary": {
      "metadata": "Run labels; this run uses exactly one synthetic world, not many.",
      "base": "The headline numbers: debt cover, return, cash available versus debt payments, equity in."
    }
  }
}
```

---

## Step 7 — Calibration preview (Yahoo → margins, no simulation)

Resolves **`dynamic_margins.yahoo_finance`** into numeric **`margins`** (e.g. set **`capex_log_sigma`** from copper volatility). **Does not** run Monte Carlo.

Save the JSON below as `calib-preview.json` **or** paste inline; body = full **`ShockPackSpec`**.

**Request payload** — `calib-preview.json`:

```json
{
  "shockpack_id": "presentation-copper-calib",
  "seed": 42,
  "n_scenarios": 5000,
  "sampling_method": "monte_carlo",
  "dynamic_margins": {
    "yahoo_finance": [
      {
        "symbol": "HG=F",
        "period": "1y",
        "target": "capex_log_sigma",
        "scale": 1.0,
        "annualization_factor": 252,
        "min_observations": 20
      }
    ]
  }
}
```

```bash
curl -s -X POST http://127.0.0.1:8000/v1/calibration/preview \
  -H "Content-Type: application/json" \
  --data-binary @calib-preview.json
```

**Example response** (200) — `capex_log_sigma` **changes** when Yahoo history / volatility changes:

```json
{
  "resolved_shockpack": {
    "shockpack_id": "presentation-copper-calib",
    "seed": 42,
    "n_scenarios": 5000,
    "sampling_method": "monte_carlo",
    "dynamic_margins": null,
    "margins": {
      "revenue_log_mean": 0.0,
      "revenue_log_sigma": 0.08,
      "capex_log_mean": 0.0,
      "capex_log_sigma": 0.39414528182635145,
      "opex_log_mean": 0.0,
      "opex_log_sigma": 0.05,
      "rate_shock_sigma": 0.005
    }
  },
  "calibration_trace": {
    "steps": [
      {
        "source": "yahoo_finance",
        "symbol": "HG=F",
        "period": "1y",
        "target": "capex_log_sigma",
        "annualized_sigma": 0.39414528182635145,
        "scale": 1.0,
        "annualization_factor": 252.0
      }
    ],
    "resolved_margins": {
      "revenue_log_mean": 0.0,
      "revenue_log_sigma": 0.08,
      "capex_log_sigma": 0.39414528182635145,
      "opex_log_sigma": 0.05,
      "rate_shock_sigma": 0.005,
      "capex_log_mean": 0.0,
      "opex_log_mean": 0.0
    }
  },
  "response_help": {
    "what_you_sent": "…",
    "what_you_received": "…",
    "findings_and_next_steps": "…"
  }
}
```

---

## Step 8 — Monte Carlo — default margins (fast demo)

Full simulation: **`AdhocSimulationRequest`** = `shockpack` + `asset`. Uses default correlation matrix and default sigmas unless you override.

**Request payload** (inline `curl`):

```bash
curl -s -X POST http://127.0.0.1:8000/v1/simulate/asset \
  -H "Content-Type: application/json" \
  -d "{\"shockpack\":{\"shockpack_id\":\"demo-mc-1\",\"seed\":42,\"n_scenarios\":2000,\"sampling_method\":\"monte_carlo\"},\"asset\":{\"asset_id\":\"demo-asset-1\",\"assumption_set_id\":\"demo-as-1\",\"horizon_years\":8,\"base_revenue_annual\":12000000,\"base_opex_annual\":5000000,\"initial_capex\":80000000,\"equity_fraction\":0.35,\"tax_rate\":0.0,\"financing\":{\"debt_principal\":40000000,\"interest_rate_annual\":0.055,\"loan_term_years\":12,\"covenant_dscr\":1.2}},\"include_attribution\":false}"
```

**Example response** (200) — sample from the same inputs as the request (`seed` 42, `n_scenarios` 2000); your numeric values match this only if the model version and data are unchanged:

```json
{
  "metadata": {
    "run_id": "1311a6e3-d4b1-4907-b038-5e5be013712d",
    "shockpack_id": "demo-mc-1",
    "assumption_set_id": "demo-as-1",
    "asset_id": "demo-asset-1",
    "execution_mode": "adhoc_asset",
    "n_scenarios": 2000,
    "seed": 42,
    "sampling_method": "monte_carlo",
    "compute_time_ms": 130.85,
    "margin_calibration_trace": null,
    "performance_profile": null
  },
  "metrics": {
    "dscr": {
      "p05": 0.9274621113067996,
      "p10": 0.977188702660524,
      "p50": 1.1597258945732198,
      "p90": 1.3636776827989072,
      "p95": 1.4221571227973062,
      "mean": 1.1679548385165808,
      "std": 0.15373079489686944
    },
    "irr_annual": {
      "p05": -0.4237273349805914,
      "p10": -0.35942495036629113,
      "p50": -0.20290950725346718,
      "p90": -0.08876013881371017,
      "p95": -0.06137182753902417,
      "mean": -0.21434720151668912,
      "std": 0.11014898845845428
    },
    "covenant_breach_probability": 0.607,
    "probability_of_default_proxy_dscr_lt_1": 0.13,
    "var_irr_95": 0.22081782772712422,
    "cvar_irr_95": -0.48689171657854985,
    "ebitda": {
      "p05": 5551548.651550195,
      "p10": 5929355.701863205,
      "p50": 6997902.118349576,
      "p90": 8256087.78684117,
      "p95": 8660690.897868492,
      "mean": 7041237.515920513,
      "std": 924077.3030272841
    },
    "var_ebitda_95": 1446353.4667993812,
    "cvar_ebitda_95": 5234756.355950448,
    "levered_cf": {
      "p05": -440714.9139744117,
      "p10": -137754.12050504857,
      "p50": 960367.2022716748,
      "p90": 2159028.6390972342,
      "p95": 2481023.0382485026,
      "mean": 998017.9768722384,
      "std": 910023.4637088283
    },
    "var_levered_cf_95": 1401082.1162460865,
    "cvar_levered_cf_95": -803883.1166556719,
    "nav_proxy_equity": {
      "p05": 24472162.423373844,
      "p10": 27161537.14214739,
      "p50": 35646313.49339708,
      "p90": 45488873.79269625,
      "p95": 48395550.161270976,
      "mean": 36046122.501689464,
      "std": 7169638.068689808
    },
    "var_nav_proxy_95": 11174151.070023235,
    "cvar_nav_proxy_95": 21963570.237714343,
    "liquidity_runway_months": null,
    "merton_equity_pd_proxy": 0.17109794313984303,
    "waterfall_dsra_avg_drag": null
  },
  "attribution": null,
  "full_stack": null,
  "extensions": null,
  "response_help": {
    "what_you_sent": "You sent one project's finances (revenue, costs, debt, etc.) plus how many random ‘what-if’ worlds to run and how strongly costs and rates can move together.",
    "what_you_received": "You get a summary of thousands of possible futures: typical and stressed debt cover (DSCR), chance of breaking loan rules, and (if requested) which kinds of shocks showed up most in bad outcomes.",
    "findings_and_next_steps": "Start with the chance of covenant breach and the low/middle/high debt-cover numbers. If something looks too risky, change assumptions or talk to your modeller before deciding. Optional ‘attribution’ is a story aid only—not a bank approval.",
    "glossary": {
      "metadata": "Labels for this run: IDs, how many worlds were run, random seed, timing.",
      "metrics": "The risk numbers: debt cover bands, breach rate, cash flow summaries.",
      "attribution": "Which drivers tend to appear when outcomes are worst (if you asked for it).",
      "full_stack": "Extra delivery and operations-style results when you use the expanded 12-risk setup.",
      "extensions": "Optional extra notes (e.g. interest-rate ladder summary, reserve-style charges, cache hints)."
    }
  }
}
```

> **`metadata`:** Full responses also include `model_version`, `created_at_utc`, optional `layer_versions`, etc. Open **`http://127.0.0.1:8000/docs`** → `SimulationResult` for every field.

---

## Step 9 — Monte Carlo with Yahoo-calibrated capex volatility

Same asset; shock pack pulls **copper** vol into **`capex_log_sigma`** before drawing scenarios.

**Request payload** — `simulate-copper.json`:

```json
{
  "shockpack": {
    "shockpack_id": "presentation-mc-copper",
    "seed": 42,
    "n_scenarios": 5000,
    "sampling_method": "monte_carlo",
    "dynamic_margins": {
      "yahoo_finance": [
        {
          "symbol": "HG=F",
          "period": "1y",
          "target": "capex_log_sigma",
          "scale": 1.0,
          "annualization_factor": 252,
          "min_observations": 20
        }
      ]
    }
  },
  "asset": {
    "asset_id": "demo-asset-1",
    "assumption_set_id": "demo-as-1",
    "horizon_years": 8,
    "base_revenue_annual": 12000000,
    "base_opex_annual": 5000000,
    "initial_capex": 80000000,
    "equity_fraction": 0.35,
    "tax_rate": 0.0,
    "financing": {
      "debt_principal": 40000000,
      "interest_rate_annual": 0.055,
      "loan_term_years": 12,
      "covenant_dscr": 1.2
    }
  },
  "include_attribution": false
}
```

```bash
curl -s -X POST http://127.0.0.1:8000/v1/simulate/asset \
  -H "Content-Type: application/json" \
  --data-binary @simulate-copper.json
```

**Example response** (200) — **abridged** (same run inputs as `simulate-copper.json` above); full `metrics` matches Step 8’s shape. Highlights: **`metadata.margin_calibration_trace`** after Yahoo calibration.

```json
{
  "metadata": {
    "run_id": "d830eb7d-b227-41d3-b6d8-2eed1cd2473a",
    "shockpack_id": "presentation-mc-copper",
    "execution_mode": "adhoc_asset",
    "n_scenarios": 5000,
    "seed": 42,
    "compute_time_ms": 2305.62,
    "margin_calibration_trace": {
      "steps": [
        {
          "source": "yahoo_finance",
          "symbol": "HG=F",
          "period": "1y",
          "target": "capex_log_sigma",
          "annualized_sigma": 0.39414528182635145,
          "scale": 1.0,
          "annualization_factor": 252.0
        }
      ],
      "resolved_margins": {
        "revenue_log_sigma": 0.08,
        "capex_log_sigma": 0.39414528182635145,
        "opex_log_sigma": 0.05,
        "rate_shock_sigma": 0.005,
        "revenue_log_mean": 0.0,
        "capex_log_mean": 0.0,
        "opex_log_mean": 0.0
      }
    }
  },
  "metrics": {
    "dscr": {
      "p05": 0.6090157409659048,
      "p10": 0.695403183799157,
      "p50": 1.1445296844173267,
      "p90": 1.893766127432882,
      "p95": 2.1618317839414645,
      "mean": 1.2335389909540018,
      "std": 0.5012287300058875
    },
    "covenant_breach_probability": 0.5482
  },
  "attribution": null,
  "full_stack": null,
  "response_help": {
    "what_you_sent": "You sent one project's finances (revenue, costs, debt, etc.) plus how many random ‘what-if’ worlds to run and how strongly costs and rates can move together.",
    "what_you_received": "You get a summary of thousands of possible futures: typical and stressed debt cover (DSCR), chance of breaking loan rules, and (if requested) which kinds of shocks showed up most in bad outcomes.",
    "findings_and_next_steps": "Start with the chance of covenant breach and the low/middle/high debt-cover numbers. If something looks too risky, change assumptions or talk to your modeller before deciding. Optional ‘attribution’ is a story aid only—not a bank approval.",
    "glossary": {
      "metadata": "Labels for this run: IDs, how many worlds were run, random seed, timing.",
      "metrics": "The risk numbers: debt cover bands, breach rate, cash flow summaries.",
      "attribution": "Which drivers tend to appear when outcomes are worst (if you asked for it).",
      "full_stack": "Extra delivery and operations-style results when you use the expanded 12-risk setup.",
      "extensions": "Optional extra notes (e.g. interest-rate ladder summary, reserve-style charges, cache hints)."
    }
  }
}
```

Expand **`metrics`** in your live response the same way as Step 8 (`irr_annual`, `ebitda`, `levered_cf`, `nav_proxy_equity`, tail and PD-style fields, etc.).

---

## Suggested presentation flow

| Order | Call | Talking point |
|------:|------|----------------|
| 1 | `/health` | Stack is live. |
| 2 | `/v1/calibration/stress-data-catalog` | We document sources; engine stays parameter-driven. |
| 3 | Yahoo `HG=F` history | Real copper series for the room. |
| 4 | `/v1/simulate/v0/base-case` | One deterministic baseline — ties to Excel. |
| 5 | `/v1/calibration/preview` | Governance: approve Yahoo-derived sigmas before big runs. |
| 6 | `/v1/simulate/asset` | Many correlated worlds → DSCR distribution and covenant risk. |

---

## Troubleshooting

| Symptom | Likely cause |
|--------|----------------|
| `401` / `403` on routes (not health) | Set `X-API-Key` when `AZRAQ_API_KEY` is configured. |
| `501` on Yahoo routes | `pip install yfinance` |
| `404` on Yahoo | Bad symbol, no data for `period`, or network blocked. |
| Validation error on simulate | `n_scenarios` must be **100–500_000**; send both `shockpack` and `asset`. |

Full contract detail: [API.md](API.md).
