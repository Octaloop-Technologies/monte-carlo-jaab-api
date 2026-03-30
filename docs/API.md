# Azraq Monte Carlo API reference

Base URL when running locally: `http://127.0.0.1:8000`  
Interactive docs: `http://127.0.0.1:8000/docs`

## Authentication and headers

| Item | When it applies |
|------|------------------|
| **`AZRAQ_API_KEY`** (in `.env`) | If set, all routes below except **`GET /health`** require header **`X-API-Key: <same value>`**. |
| **`X-Azraq-User-Id`** | Optional. Label stored on runs for **audit** (not login). |

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
| `copula` | string | `"gaussian"` \| `"student_t"` |
| `t_degrees_freedom` | number | for `student_t`; > 2 |

**Full-stack mode:** use **12** factors in `factor_order` (see `GET /v1/catalog/full-stack-factors`) and set `asset.full_stack.enabled: true`. Easiest way to build a valid 12× shockpack in Python:

```bash
python -c "import json; from azraq_mc.presets import make_full_stack_shockpack; print(json.dumps(make_full_stack_shockpack('demo-fs', 11, 500).model_dump(), indent=2))"
```

Paste the printed JSON as the `shockpack` body field.

---

## Endpoints

### `GET /health`

**Auth:** none (always public).

**Response** (200):

```json
{ "status": "ok" }
```

---

### `GET /v1/catalog/full-stack-factors`

**Auth:** optional API key (if `AZRAQ_API_KEY` is set).

**Response** (200): catalogue of full-stack factor IDs and metadata.

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

### `POST /v1/simulate/v0/base-case`

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

Monte Carlo **single asset**. Body: **`AdhocSimulationRequest`**.

| Field | Type | Notes |
|-------|------|--------|
| `shockpack` | `ShockPackSpec` | required |
| `asset` | `AssetAssumptions` | required |
| `include_attribution` | boolean | default `false` |
| `attribution_tail_fraction` | number | default `0.05`; range ~0.01–0.25 |

**Response** (200): `SimulationResult`

- `metadata` — `execution_mode: "adhoc_asset"`, seed, `n_scenarios`, etc.
- `metrics` — `FinancialRiskMetrics`: `dscr` / `irr_annual` as **DistributionSummary** (`p05`…`p95`, `mean`, `std`), `covenant_breach_probability`, optional IRR VaR/CVaR, PD proxy fields.
- `attribution` — present if `include_attribution: true`.
- `full_stack` — present if `asset.full_stack` enabled.

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

### `POST /v1/shockpack/export/npz`

Builds correlated shocks and writes **NumPy `.npz`** (+ sidecar metadata) under a directory.

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

Persists a prior **`SimulationResult`**, **`PortfolioSimulationResult`**, or **`BaseCaseResult`** JSON to **`AZRAQ_SNAPSHOT_DIR`** (default `data/snapshots`).

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

Compares two **saved** `asset_simulation` snapshots (both must be **`SimulationResult`**).

Body:

```json
{
  "before_path": "E:\\\\...\\\\snapshots\\\\older.json",
  "after_path": "E:\\\\...\\\\snapshots\\\\newer.json"
}
```

**Response** (200): nested dictionary of metric changes. Numeric leaves look like:

```json
{
  "covenant_breach_probability": {
    "before": 0.12,
    "after": 0.22,
    "delta": 0.1
  },
  "dscr.p50": { "before": 1.18, "after": 1.1, "delta": -0.08 }
}
```

**Error** (400): if either file is not an asset Monte Carlo result.

---

### `WebSocket` `WS /ws/v1/simulate/portfolio`

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
