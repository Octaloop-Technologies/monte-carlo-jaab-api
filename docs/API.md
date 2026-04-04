# Azraq Monte Carlo API reference

Base URL when running locally: `http://127.0.0.1:8000`  
Interactive docs: `http://127.0.0.1:8000/docs`

Run from the repo root: `python -m uvicorn azraq_mc.api:app --reload --host 127.0.0.1 --port 8000`.

## Authentication and headers

| Item | When it applies |
|------|------------------|
| **`AZRAQ_API_KEY`** (in `.env`) | If set, all routes below except **`GET /health`** require header **`X-API-Key: <same value>`**. |
| **`X-Azraq-User-Id`** | Optional. Label stored on runs for **audit** (not login). |
| **`X-Azraq-Tenant-Id`** | Optional. **Catalogue**: filters **`GET /v1/shockpack/catalog`** and must **match** stored tenant on **`GET .../catalog/{entry_id}`** when set. |
| **`X-Azraq-Catalog-Role`** | Required for **`POST .../catalog/{id}/promote`** unless **`AZRAQ_CATALOG_PROMOTER_ROLES`** env is empty (local dev). Value must be in that allow-list (default includes `admin`, `promoter`). |

## Shared types (used in many payloads)

### `FinancingAssumptions`

| Field | Type | Notes |
|-------|------|--------|
| `debt_principal` | number | ≥ 0 |
| `interest_rate_annual` | number | decimal, e.g. `0.055` = 5.5% |
| `loan_term_years` | integer | ≥ 1 |
| `covenant_dscr` | number | breach if modeled DSCR below this |

### `AssetAssumptions` (main project inputs)

| Field | Type | Required | Notes |
|-------|------|----------|--------|
| `asset_id` | string | ✓ | Identifier |
| `assumption_set_id` | string | ✓ | Version label for assumptions |
| `horizon_years` | integer | ✓ | ≥ 1 |
| `base_revenue_annual` | number | ✓ | > 0 |
| `base_opex_annual` | number | ✓ | ≥ 0 |
| `initial_capex` | number | ✓ | > 0 |
| `equity_fraction` | number | ✓ | (0, 1] |
| `tax_rate` | number | | default `0`, in [0, 1) |
| `financing` | object | ✓ | `FinancingAssumptions` |
| `utility_opex_annual` | number | | default `0`; must be ≤ `base_opex_annual` |
| `equity_discount_rate_for_npv` | number \| null | | optional; enables equity NPV in V0 |
| `project_discount_rate_for_ev` | number \| null | | optional; enables stylised EV in V0 |
| `factor_transforms` | object \| null | | optional scaling / floors |
| `full_stack` | object \| null | | optional; requires **12-factor** `ShockPackSpec` when enabled |

### `ShockPackSpec` (Monte Carlo / shocks)

| Field | Type | Default / notes |
|-------|------|------------------|
| `shockpack_id` | string | required |
| `schema_version` | string | default `"1.0"` |
| `seed` | integer | required; reproducibility |
| `n_scenarios` | integer | **100–500_000** |
| `sampling_method` | string | `"monte_carlo"` \| `"latin_hypercube"` \| `"sobol"` |
| `factor_order` | string[] | default 4 factors: `revenue`, `capex`, `opex`, `rate` |
| `correlation` | number[][] | square matrix; length must match `factor_order` |
| `margins` | object | lognormal/rate vol params (see OpenAPI schema) |
| `dynamic_margins` | object \| null | optional: pull `margins` from **file**, **HTTP JSON**, or **Yahoo Finance** before running (see below) |
| `copula` | string | `"gaussian"` \| `"student_t"` |
| `t_degrees_freedom` | number | for `student_t`; > 2 |
| `time_grid` | object \| null | multi-period shocks: `{ "n_periods", "period_length_years", "dynamics": "iid" \| "ar1", "ar1_phi" }` — Z shape `(n_scenarios, n_factors, n_periods)` |
| `macro_regime` | string | audit label (e.g. `baseline`, `rates_shock`); combine with ShockPack catalogue |

#### `dynamic_margins` — calibration from external sources

Applied in order: **`file`** → **`http`** → each **`yahoo_finance`** binding (later steps override the same keys). The resolved numbers are written to `margins`; `dynamic_margins` is cleared on the materialised spec. Run metadata includes **`margin_calibration_trace`** (steps + `resolved_margins`) for audit when sources are used.

| Field | Type | Notes |
|-------|------|--------|
| `file` | object \| null | `{ "path": "<path>", "mode": "overlay" \| "replace", "sheet": 0 }` — **JSON** (margin object or `{ "margins": { ... } }`) or **Excel** `.xlsx`/`.xlsm`: either columns `key`/`field`/`margin` + `value`/`sigma`, **or** a **wide** table whose headers are `RiskFactorMargins` field names (`revenue_log_sigma`, …) and the **first data row** holds numbers. `sheet` is the Excel sheet name or index (ignored for JSON). |
| `http` | object \| null | `{ "url": "https://...", "timeout_sec": 30, "headers": {}, "mode": "overlay" \| "replace" }` — same JSON shape as file |
| `yahoo_finance` | array | Each item: `{ "symbol": "^GSPC", "period": "1y", "target": "revenue_log_sigma" \| "capex_log_sigma" \| "opex_log_sigma" \| "rate_shock_sigma", "scale": 1.0, "annualization_factor": 252, "min_observations": 20 }` — annualised log-return volatility |

**Security:** HTTP/file paths are evaluated in the API process environment. Only allow trusted URLs and paths in production (SSRF / arbitrary file read risk).

**Dependency:** Yahoo bindings require `yfinance` (listed in `requirements.txt`).

#### Appendix J — stress data sources (beyond Yahoo)

The product **Appendix J** lists official and market series (ECB, NY Fed / SOFR, BoE / SONIA, IEA, etc.). The Monte Carlo **core does not need live feeds**: it runs on **parameterised** distributions. External data only **calibrates** margins (or informs manual overlays) via:

| Mechanism | Typical sources | API / spec |
|-----------|-----------------|------------|
| **Yahoo Finance** | Commodities, VIX, some rates proxies | `GET /v1/market/yfinance/...`, `dynamic_margins.yahoo_finance` |
| **ECB daily XML** | EUR/USD reference | `GET /v1/market/ecb/eur-usd` |
| **HTTP JSON** | Your proxy of SOFR, IEA, BoE CSV→JSON, internal ETL | `dynamic_margins.http` → trusted URL returning margin JSON |
| **File** | JSON margin patch **or** Excel (wide or key/value columns) | `dynamic_margins.file` |

**Machine-readable catalogue** (IDs, URLs, primary/secondary tier, mapping hints): **`GET /v1/calibration/stress-data-catalog`**.  
That endpoint returns `sources[]`, `integration_overview`, and plain-English **`response_help`**.

**Full-stack mode:** use **12** factors in `factor_order` (see `GET /v1/catalog/full-stack-factors`) and set `asset.full_stack.enabled: true`. Easiest way to build a valid 12× shockpack in Python:

```bash
python -c "import json; from azraq_mc.presets import make_full_stack_shockpack; print(json.dumps(make_full_stack_shockpack('demo-fs', 11, 500).model_dump(), indent=2))"
```

Paste the printed JSON as the `shockpack` body field.

---

## Endpoints

Each route below uses the same four blocks so non-technical readers can follow along:

| Block | Meaning |
|-------|---------|
| **Description** | What this call is for in the product. |
| **You send** | URL parts, query strings, JSON body — what you must supply. |
| **You get** | What comes back (main fields and typical errors). |
| **Analysis** | How to read the result: what it implies for calibration, risk, or audit. |

### `response_help` in JSON bodies

Most responses include a top-level object **`response_help`** written for **non-technical** readers:

| Key | Purpose |
|-----|---------|
| **`what_you_sent`** | In plain language, what request / inputs this response belongs to. |
| **`what_you_received`** | In plain language, Payload overview—what kind of answer this is. |
| **`findings_and_next_steps`** | What to conclude, what to do next, and cautions (without jargon). |
| **`glossary`** *(optional)* | Short definitions of important names you see elsewhere in the same JSON. |

Structured OpenAPI models (`SimulationResult`, `PortfolioSimulationResult`, `BaseCaseResult`, `CalibrationPreviewResponse`, `ScheduledAssetResponse`) expose **`response_help`** via the schema so it appears in **`model_dump()` / HTTP JSON** automatically. Plain dict routes (health, market, catalogue, snapshots, audit, diff) attach the same pattern manually.

Saved snapshots include **`response_help`** when saved from a client that serializes the full model; on reload, extra keys are ignored and **`response_help`** is recomputed for result types that use `computed_field`.

---

### `GET /health`

**Description:** Liveness check — confirms the HTTP server is running.

**You send:** Nothing. No API key required.

**You get:** `200` — `status`, plus **`response_help`** (`what_you_sent`, `what_you_received`, `findings_and_next_steps`). If the process is down, you get a connection error instead of JSON.

**Analysis:** Use before demos or monitoring: “Is the stack up?” This does **not** run a model or touch the database.

**Auth:** none (always public).

```json
{
  "status": "ok",
  "response_help": {
    "what_you_sent": "…",
    "what_you_received": "…",
    "findings_and_next_steps": "…"
  }
}
```

---

### `GET /v1/market/yfinance/{symbol}/history`

**Description:** Raw **market history** (OHLCV) from Yahoo Finance for a ticker — useful to inspect data before tying it to shocks (e.g. copper `HG=F`).

**You send:** Path **`symbol`** (e.g. `HG=F`, `^GSPC`). Query **`period`** — `1d`, `5d`, `1mo`, `3mo`, `6mo`, `1y`, `2y`, `5y`, `10y`, `ytd`, `max` (default `1y`).

**You get:** `200` — `{ "symbol", "period", "data": [ ... rows with dates and prices ... ] }`. **`404`** if Yahoo returns no series. **`501`** if `yfinance` is not installed.

**Analysis:** This is **exploratory data**, not a simulation. You use it to sanity-check that the symbol resolves and the history looks reasonable; actual **volatility calibration** into the model usually goes through `dynamic_margins.yahoo_finance` or `POST /v1/calibration/preview`.

**Auth:** optional API key (if `AZRAQ_API_KEY` is set).

---

### `GET /v1/market/yfinance/{symbol}/returns`

**Description:** **Daily (bar) simple returns** from closing prices — closer to what volatility calibration uses internally than raw levels.

**You send:** Path **`symbol`**, query **`period`** (same set as history).

**You get:** `200` — `{ "symbol", "period", "returns": [{"date", "return"}, ...], "n" }`. **`404`** / **`501`** as above.

**Analysis:** Compare return volatility informally with your assumptions. The engine’s Yahoo calibration uses **log** returns and annualisation rules; this endpoint is for **human inspection** and third-party reporting, not an exact duplicate of the calibration formula.

**Auth:** optional API key (if `AZRAQ_API_KEY` is set).

---

### `GET /v1/market/ecb/eur-usd`

**Description:** **European Central Bank** daily **EUR/USD** reference rate from the public `eurofxref-daily.xml` feed (no Yahoo).

**You send:** Optional API key if configured.

**You get:** `rate_date`, `one_eur_in_usd`, `source_url`, plus **`response_help`**.

**Analysis:** Use for FX sanity checks or to build a margin file / `http_json` bridge. **Does not** auto-update `ShockPackSpec` until you wire results into **`dynamic_margins`** or a catalogue entry.

**Auth:** optional API key (if `AZRAQ_API_KEY` is set).

---

### `GET /v1/calibration/stress-data-catalog`

**Description:** **Appendix J–style** directory: categories (construction, power, FX, rates, systemic stress), example stress narratives, **official/example URLs** (IEA, NY Fed SOFR, BoE, ECB, Yahoo copper, etc.), and how each row typically maps to **`dynamic_margins`** / **full_stack** factors.

**You send:** Nothing beyond optional API key.

**You get:** `sources` (array of rows), `integration_overview` (how Yahoo / ECB / http / file / manual fit together), **`response_help`**.

**Analysis:** Pick a source, then use the listed **`integration_paths`**: Yahoo tickers for quick vol calibration, ECB route for spot EUR/USD, or host **IEA/NY Fed/BoE** series as JSON for **`dynamic_margins.http`**.

**Auth:** optional API key (if `AZRAQ_API_KEY` is set).

---

### `GET /v1/catalog/full-stack-factors`

**Description:** Returns the **ordered list of risk factor IDs** and human-readable **catalog entries** for **full-stack** mode (delivery, power, cyber, etc.).

**You send:** Nothing except optional API key.

**You get:** `200` — JSON with `factor_order` (array of strings) and `risk_factors` (metadata objects).

**Analysis:** Before building a **12×12** correlation matrix or enabling `asset.full_stack`, use this to see **exact factor names** and descriptions. Wrong names or matrix size → validation errors on simulate.

```json
{
  "factor_order": ["revenue", "capex", "opex", "rate", "fx", "power_price", "..."],
  "risk_factors": [
    {
      "factor_id": "revenue",
      "display_name": "Market demand / colo pricing",
      "description": "...",
      "distribution_family": "normal_shock",
      "calibration_version": "1.0"
    }
  ]
}
```

---

### `POST /v1/calibration/preview`

**Description:** **Dry-run calibration** — turns `dynamic_margins` (file / HTTP / Yahoo) into concrete **`margins`** on the shock pack **without** running Monte Carlo. Use to approve data sourcing before a heavy simulation.

**You send:** JSON body = full **`ShockPackSpec`** (same shape as `shockpack` on simulate), often including **`dynamic_margins`**.

**You get:** `200` — `CalibrationPreviewResponse`:  
- **`resolved_shockpack`** — copy of the spec with numbers filled in and **`dynamic_margins` removed** (safe to paste into `/v1/simulate/*`).  
- **`calibration_trace`** — audit trail (`steps`, `resolved_margins`) or `null` if nothing to resolve.

**Analysis:** Review **`resolved_shockpack.margins`** (e.g. `capex_log_sigma` after a copper Yahoo binding) and **`calibration_trace`** for governance. No **distributions of DSCR/IRR** here — only **inputs** to the engine.

**Auth:** optional API key (if `AZRAQ_API_KEY` is set).

No scenarios are drawn; this is suitable for validating file/HTTP/Yahoo calibration before a heavy run.

---

### `POST /v1/simulate/v0/base-case`

**Description:** **Deterministic baseline** — no random shocks; factors are effectively at a fixed reference (zero-shock path). One **scenario**, fast, good for “model ties out” checks.

**You send:** JSON body = **`AssetAssumptions`** only (not wrapped in `asset`; the body *is* the asset).

**You get:** `200` — `BaseCaseResult`: **`metadata`** (`execution_mode: "v0_base"`, `n_scenarios: 1`, …) and **`base`** with single numbers: `dscr`, `irr_annual`, `annual_revenue`, `ebitda`, `debt_service`, `initial_equity`, multipliers (usually `1`), `effective_interest_rate`, optional `npv_equity`, `enterprise_value`.

**Analysis:** Use as a **sanity baseline**. Compare to spreadsheet DSCR at “median” assumptions. This is **not** tail risk — for that use **`/v1/simulate/asset`**.

Deterministic **single path** (no Monte Carlo). Request body = **`AssetAssumptions`** (not wrapped).

**Response** (200): `BaseCaseResult`

- `metadata` — run ids, `execution_mode: "v0_base"`, `n_scenarios: 1`, etc.
- `base` — point estimates: `dscr`, `irr_annual`, `annual_revenue`, `ebitda`, `debt_service`, `initial_equity`, multipliers (usually `1`), `effective_interest_rate`, optional `npv_equity`, `enterprise_value`.

**Example request:**

```json
{
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
}
```

**Example response (abridged):**

```json
{
  "metadata": {
    "run_id": "...",
    "shockpack_id": "v0-deterministic",
    "execution_mode": "v0_base",
    "n_scenarios": 1,
    "asset_id": "demo-asset-1",
    "assumption_set_id": "demo-as-1"
  },
  "base": {
    "dscr": 1.16,
    "irr_annual": -0.22,
    "annual_revenue": 12000000,
    "ebitda": 7000000,
    "debt_service": 6033520.02,
    "initial_equity": 28000000,
    "revenue_multiplier": 1,
    "capex_multiplier": 1,
    "opex_multiplier": 1,
    "effective_interest_rate": 0.055,
    "npv_equity": null,
    "enterprise_value": null
  }
}
```

---

### `POST /v1/simulate/asset`

**Description:** Main **Monte Carlo** run for **one project** — draws many correlated shock paths and produces **distributions of DSCR, IRR, breach probability**, etc.

**You send:** JSON **`AdhocSimulationRequest`**: **`asset`** (required) + either **`shockpack`** or **`shockpack_catalog_entry_id`** (or both; catalogue + inline patch). Optional: **`include_attribution`**, **`include_advanced_attribution`**, **`attribution_tail_fraction`**, **`performance_profile`**.

**You get:** `200` — **`SimulationResult`**: **`metadata`** (run id, seed, `n_scenarios`, timing, optional catalogue id), **`metrics`** (distributions and breach/PD-style proxies), optional **`attribution`** and **`full_stack`**, optional **`extensions`** (macro/waterfall/cache diagnostics).

**Analysis:** **Covenant breach probability** and **DSCR percentiles** answer “how bad can liquidity coverage get under this shock design?” **Attribution** (if on) supports narrative “what drove the tail” — interpret as **indicative**, not a regulatory sign-off. Turn on **`full_stack`** only with a **12-factor** shock pack matching `GET /v1/catalog/full-stack-factors`.

Monte Carlo **single asset**. Body: **`AdhocSimulationRequest`**.

| Field | Type | Notes |
|-------|------|--------|
| `shockpack` | `ShockPackSpec` \| omit if catalogue id set | inline spec |
| `shockpack_catalog_entry_id` | string \| null | load base spec from `POST /v1/shockpack/catalog/register`; inline `shockpack` patches unset fields |
| `asset` | `AssetAssumptions` | required |
| `include_attribution` | boolean | default `false` |
| `attribution_tail_fraction` | number | default `0.05`; range ~0.01–0.25 |
| `performance_profile` | `"interactive"` \| `"standard"` \| `"deep"` \| null | `interactive` caps `n_scenarios` at 5000, `standard` at 25000 (for faster UI); `deep` = no cap |
| `include_advanced_attribution` | boolean | default `false`; when `true` with `include_attribution`, adds Euler- and Shapley-style **factor weights** on CF loss (see OpenAPI) |

**Response** (200): `SimulationResult`

- `metadata` — `execution_mode: "adhoc_asset"`, seed, `n_scenarios`, **`compute_time_ms`**, optional **`shockpack_catalog_entry_id`**, **`performance_profile`**, etc.
- `metrics` — `FinancialRiskMetrics`: `dscr` / `irr_annual`, **EBITDA** / **levered_cf** / **nav_proxy_equity** summaries and VaR/CVaR-style tail fields (see OpenAPI), `covenant_breach_probability`, PD proxy.
- `attribution` — tail regression plus **risk buckets**, **interaction** heuristic, **var_metric_decomposition** on levered CF when requested.
- `full_stack` — schedule/SLA/cyber/**PUE·WUE breach** / joint grid–gen stress when `asset.full_stack` enabled.

**Example request:**

```json
{
  "shockpack": {
    "shockpack_id": "demo-sp-1",
    "seed": 42,
    "n_scenarios": 800,
    "sampling_method": "monte_carlo"
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

**Example response (abridged):**

```json
{
  "metadata": {
    "run_id": "...",
    "execution_mode": "adhoc_asset",
    "seed": 42,
    "n_scenarios": 800,
    "shockpack_id": "demo-sp-1"
  },
  "metrics": {
    "dscr": {
      "p05": 1.05,
      "p10": 1.08,
      "p50": 1.18,
      "p90": 1.28,
      "p95": 1.31,
      "mean": 1.17,
      "std": 0.06
    },
    "irr_annual": { "...": "..." },
    "covenant_breach_probability": 0.15,
    "probability_of_default_proxy_dscr_lt_1": 0.02,
    "var_irr_95": null,
    "cvar_irr_95": null
  },
  "attribution": null,
  "full_stack": null
}
```

*(Numbers illustrative; actual values depend on inputs.)*

---

### `POST /v1/simulate/scheduled/asset`

**Description:** Same maths as **`/v1/simulate/asset`**, aimed at **recurring runs** (e.g. monitoring). Optionally **persists** the full `SimulationResult` JSON to disk for later diffing.

**You send:** **`ScheduledAssetRequest`** = everything **`AdhocSimulationRequest`** accepts, plus **`label`**, **`persist`**, **`model_version`**.

**You get:** `200` — **`ScheduledAssetResponse`**: **`result`** (full `SimulationResult`) and **`snapshot_path`** (file path if `persist` is true, else `null`).

**Analysis:** Use **snapshots** with **`/v1/snapshots/diff/asset-metrics`** to answer “how did risk metrics **drift** between two dates?” — see **provenance_delta** (what changed in inputs vs model).

Same core inputs as **`/v1/simulate/asset`**, plus monitoring-style fields. Runs the simulation and optionally **writes a JSON snapshot** to disk.

Extra fields on **`ScheduledAssetRequest`**:

| Field | Type | Default |
|-------|------|---------|
| `label` | string \| null | file naming hint |
| `persist` | boolean | `true` |
| `model_version` | string | `"azraq-mc-v1"` |

**Response** (200): `ScheduledAssetResponse`

```json
{
  "result": { "metadata": {}, "metrics": {}, "attribution": null, "full_stack": null },
  "snapshot_path": "E:\\\\...\\\\data\\\\snapshots\\\\asset_simulation_....json"
}
```

If `persist` is `false`, `snapshot_path` may be `null`. Snapshot root: env **`AZRAQ_SNAPSHOT_DIR`** or default `data/snapshots`.

---

### `POST /v1/simulate/portfolio`

**Description:** **One joint draw** per scenario index across **all assets** — same shock realisation row affects every site. Use for **portfolio concentration** and “any breach” / **min DSCR across book** style questions.

**You send:** **`PortfolioSimulationRequest`**: **`shockpack`** (or catalogue id) + **`portfolio_id`**, **`portfolio_assumption_set_id`**, **`assets`** (array, **at least 2** `AssetAssumptions`).

**You get:** `200` — **`PortfolioSimulationResult`**: **`metadata`**, **`per_asset`** (each asset’s `FinancialRiskMetrics`), **`portfolio`** (`probability_any_covenant_breach`, `min_dscr_across_assets`, concentration, summed CF tails, etc.).

**Analysis:** **`probability_any_covenant_breach`** is **not** the same as sum of single-asset breaches — correlation means **joint** stress. Compare **solo** `simulate/asset` vs **portfolio** for the same assets to see diversification vs common factors.

Joint Monte Carlo over **≥ 2 assets**. Body: **`PortfolioSimulationRequest`**.

| Field | Type |
|-------|------|
| `shockpack` | `ShockPackSpec` |
| `portfolio_id` | string |
| `portfolio_assumption_set_id` | string |
| `assets` | array of `AssetAssumptions` (min length **2**) |

**Response** (200): `PortfolioSimulationResult`

- `metadata` — `PortfolioRunMetadata` (`portfolio_id`, `asset_ids`, seed, `n_scenarios`, …)
- `per_asset` — list of `{ asset_id, assumption_set_id, metrics: FinancialRiskMetrics }`
- `portfolio` — `PortfolioMetrics`: e.g. `probability_any_covenant_breach`, `min_dscr_across_assets`, concentration / weighted breach fields, summed cashflow tails.

**Example request:**

```json
{
  "shockpack": {
    "shockpack_id": "demo-sp-portfolio",
    "seed": 42,
    "n_scenarios": 600,
    "sampling_method": "monte_carlo"
  },
  "portfolio_id": "demo-portfolio-1",
  "portfolio_assumption_set_id": "demo-pas-1",
  "assets": [
    {
      "asset_id": "demo-site-a",
      "assumption_set_id": "demo-as-a",
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
    {
      "asset_id": "demo-site-b",
      "assumption_set_id": "demo-as-b",
      "horizon_years": 8,
      "base_revenue_annual": 9000000,
      "base_opex_annual": 4200000,
      "initial_capex": 65000000,
      "equity_fraction": 0.4,
      "tax_rate": 0.0,
      "financing": {
        "debt_principal": 32000000,
        "interest_rate_annual": 0.06,
        "loan_term_years": 12,
        "covenant_dscr": 1.25
      }
    }
  ]
}
```

---

### `POST /v1/shockpack/catalog/register`

**Description:** **Save** a `ShockPackSpec` in the SQLite catalogue (and optional on-disk artefact if `AZRAQ_ARTEFACT_ROOT` + `tenant_id` are set) for reuse.

**You send:** Body = **`ShockPackSpec`**. Query: **`semver`**, optional **`tenant_id`**, **`promotion_tier`**, **`rbac_owner_role`**.

**You get:** `200` — `{ "entry_id": "<uuid>" }`. Store this as **`shockpack_catalog_entry_id`** on simulate calls.

**Analysis:** Reduces copy-paste errors and freezes a **governance-approved** shock design. Inline `shockpack` on simulate can still **patch** specific fields (e.g. seed) without re-registering.

**Auth:** optional API key.

### `POST /v1/shockpack/catalog/{entry_id}/promote`

**Description:** Move a registered pack **`promotion_tier`**: `dev` → `staging` → `prod` (or set explicitly).

**You send:** Path **`entry_id`**, query **`to_tier`**. Header **`X-Azraq-Catalog-Role`** must be in **`AZRAQ_CATALOG_PROMOTER_ROLES`** (default allow-list: `admin`, `promoter`); if that env is **empty**, promotion is allowed without role (local dev only).

**You get:** `200` — `{ "ok": true }`. **`403`** if role not allowed.

**Analysis:** Operational gate: **prod**-tier entries can be filtered in **`GET /v1/shockpack/catalog`** via **`promotion_tier`** so only promoted packs appear in downstream tools.

### `GET /v1/shockpack/catalog/{entry_id}`

**Description:** **Fetch** one catalogue row: ids, semver, tenant, **`spec`** JSON, hash, optional **`object_uri`**, etc.

**You send:** Path **`entry_id`**. Optional header **`X-Azraq-Tenant-Id`** — if the entry has a **`tenant_id`** stored, it must **match** or you get **`403`**.

**You get:** `200` — object including **`spec`** (parseable `ShockPackSpec`). **`404`** / key errors if missing.

**Analysis:** Inspect exactly what will run before simulate; diff specs between versions for change control.

### `GET /v1/shockpack/catalog`

**Description:** **List** recent registrations (metadata only; not full spec per row — use **GET by id** for full `spec`).

**You send:** Query **`limit`**, optional **`tenant_id`** and **`promotion_tier`**. If **`tenant_id`** is omitted, header **`X-Azraq-Tenant-Id`** may be used to filter.

**You get:** `200` — `{ "entries": [ ... ] }`.

**Analysis:** Discover **`entry_id`** for CI/CD or analyst workflows; combine with **`promotion_tier=prod`** for “approved packs only” lists.

**Auth:** optional API key.

---

### `POST /v1/shockpack/export/npz`

**Description:** Materialises **`Z`** (correlated normal shocks) to **NumPy binary** on disk for offline Python/HPC workflows — does **not** return the array in HTTP body.

**You send:** **`ShockExportRequest`**: **`shockpack`** + optional **`directory`**.

**You get:** `200` — `{ "path": "<absolute path to .npz>" }`. **`dynamic_margins`** are resolved before draw (same as simulate).

**Analysis:** Use when another team wants **raw scenarios** for custom models. The **financial interpretation** still lives in `AssetAssumptions` + impact logic in this repo when you bring results back.

Body: **`ShockExportRequest`**

| Field | Type | Notes |
|-------|------|--------|
| `shockpack` | `ShockPackSpec` | required |
| `directory...` | string \| null | folder; default from **`AZRAQ_SHOCK_EXPORT_DIR`** or `data/shockpacks` |

**Response** (200):

```json
{ "path": "E:\\\\...\\\\data\\\\shockpacks\\\\<shockpack_id>_....npz" }
```

---

### `POST /v1/snapshots/save`

**Description:** Writes an **already computed** result object to a **JSON file** on the server (audit / diff / dashboard ingestion).

**You send:** **`SnapshotSaveRequest`**: **`label`** (optional) + **`result`** (full body from a prior simulate response).

**You get:** `200` — `{ "path": "<absolute path>" }`.

**Analysis:** Pairs with **`scheduled`** runs (auto-save) or manual “bookmark this run”. Paths from **`GET /v1/snapshots/list`**.

Body: **`SnapshotSaveRequest`**

```json
{
  "label": "my-run-label",
  "result": { "...": "full response body from a previous simulate call" }
}
```

**Response** (200):

```json
{ "path": "E:\\\\...\\\\snapshots\\\\..." }
```

---

### `GET /v1/snapshots/list`

**Description:** Lists **snapshot file paths** the server knows about under the snapshot root.

**You send:** Nothing.

**You get:** `200` — `{ "paths": [ "...", ... ] }`.

**Analysis:** Pick **`before_path`** / **`after_path`** for **`/v1/snapshots/diff/asset-metrics`**.

**Response** (200):

```json
{
  "paths": [
    "E:\\\\projects-octa\\\\monte_carlo\\\\data\\\\snapshots\\\\file1.json",
    "E:\\\\projects-octa\\\\monte_carlo\\\\data\\\\snapshots\\\\file2.json"
  ]
}
```

---

### `GET /v1/audit/runs`

**Description:** Recent **HTTP/WebSocket simulation events** logged for compliance / ops (not a full data warehouse).

**You send:** Query **`limit`** (default **50**).

**You get:** `200` — `{ "runs": [ { run_id, run_kind, asset_id, shockpack_id, seed, n_scenarios, ... }, ... ] }`. Empty **`runs`** if audit DB missing or disabled.

**Analysis:** “Who ran what, when, with which shock pack?” Cross-check **`run_id`** with **`SimulationResult.metadata.run_id`**.

Query param: **`limit`** (default **50**).

**Response** (200): recent rows from SQLite audit DB (`AZRAQ_AUDIT_DB`, default `data/azraq_audit.sqlite3`). If DB missing, `runs` is `[]`.

```json
{
  "runs": [
    {
      "run_id": "...",
      "run_kind": "adhoc_asset",
      "asset_id": "demo-asset-1",
      "portfolio_id": null,
      "shockpack_id": "demo-sp-1",
      "assumption_set_id": "demo-as-1",
      "seed": 42,
      "n_scenarios": 800,
      "created_at_utc": "2026-03-29T20:00:00",
      "client_hint": "http:asset"
    }
  ]
}
```

Disable audit with env **`AZRAQ_DISABLE_AUDIT`** (if configured in your deployment).

---

### `POST /v1/snapshots/diff/asset-metrics`

**Description:** **Compare two asset Monte Carlo snapshots** — numeric **metric deltas** plus **which assumptions/shock/settings changed** (drift decomposition).

**You send:** JSON **`before_path`**, **`after_path`** (server paths from **`snapshots/list`** or scheduled **`snapshot_path`**).

**You get:** `200` — **`metrics_delta`** (e.g. breach prob before/after/delta), **`provenance_delta`** (booleans/structured flags: assumption set, shockpack id, seed, catalogue entry, performance profile, …). **`400`** if either file is not an asset **`SimulationResult`**.

**Analysis:** Answer “**Mode 2 drift**”: did risk worsen because **assumptions** moved, **shocks** changed, or **model version** moved? Read **`provenance_delta`** first, then **`metrics_delta`**.

Compares two **saved** `asset_simulation` snapshots (both must be **`SimulationResult`**).

Body:

```json
{
  "before_path": "E:\\\\...\\\\snapshots\\\\older.json",
  "after_path": "E:\\\\...\\\\snapshots\\\\newer.json"
}
```

**Response** (200):

- **`metrics_delta`** — nested metric changes (numeric leaves as `before` / `after` / `delta`).
- **`provenance_delta`** — booleans and structured deltas for **assumption set**, **shockpack/seed**, **model_version**, **catalog entry**, **performance_profile**, etc. (Mode 2 risk-drift decomposition).

```json
{
  "metrics_delta": {
    "covenant_breach_probability": { "before": 0.12, "after": 0.22, "delta": 0.1 }
  },
  "provenance_delta": {
    "assumption_set_changed": false,
    "shockpack_id_changed": true,
    "seed_changed": false
  }
}
```

**Error** (400): if either file is not an asset Monte Carlo result.

---

### `WebSocket` `WS /ws/v1/simulate/portfolio`

**Description:** Same **portfolio joint simulation** as **`POST /v1/simulate/portfolio`**, over a WebSocket — useful for **progress** messages on long runs.

**You send:** After connect, **one** JSON message with the same shape as **`PortfolioSimulationRequest`**. If `AZRAQ_API_KEY` is set, include header **`x-api-key`** on the WebSocket handshake.

**You get:** Messages: optional **`{ "type": "progress", "done": i, "of": n }`**, then **`{ "type": "result", "body": <PortfolioSimulationResult> }`**, or **`{ "type": "error", "detail": "..." }`**.

**Analysis:** **`body`** matches the HTTP portfolio response; use when UIs cannot hold a long HTTP request open. Audit may tag **`ws:portfolio`**.

**Auth:** if `AZRAQ_API_KEY` is set, connect with header **`x-api-key`**.

1. Client sends **one JSON message** = same shape as **`PortfolioSimulationRequest`**.
2. Server may send **`{ "type": "progress", "done": i, "of": n }`** messages.
3. Final success: **`{ "type": "result", "body": <PortfolioSimulationResult as JSON> }`**.
4. On error: **`{ "type": "error", "detail": "..." }`**.

---

## Run the server

```bash
cd /path/to/monte_carlo
pip install -r requirements.txt
uvicorn azraq_mc.api:app --host 127.0.0.1 --port 8000
```

## Smoke test (all HTTP + WS)

```bash
python scripts/smoke_test_api.py
```

Run from repository root (script adds the root to `PYTHONPATH`).
