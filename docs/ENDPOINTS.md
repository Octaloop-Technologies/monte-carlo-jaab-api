# API endpoints — parameters, bodies, responses, usage

**Hosted (Swagger UI — try requests in the browser):** [https://monte-carlo.octaloop.dev/docs#/](https://monte-carlo.octaloop.dev/docs#/)

**Same deployment:** OpenAPI JSON — `https://monte-carlo.octaloop.dev/openapi.json` · optional investor dashboard — `https://monte-carlo.octaloop.dev/app/` (if enabled).

**Local dev:** `http://127.0.0.1:8000` (same paths: `/docs`, `/openapi.json`, `/app/`).

**Machine-readable contract:** **`GET /openapi.json`**. **Interactive UI:** **`GET /docs`** (Swagger).

**Full guide (single file — versions, integration, flow, endpoints):** **[Azraq_Monte_Carlo_API_Reference.md](Azraq_Monte_Carlo_API_Reference.md)**.

**Longer narrative + risk interpretation:** **[API.md](API.md)** (keep this file for the catalogue of routes).

**Quick integration flow:** **[INTEGRATION.md](INTEGRATION.md)**.

---

## Contents

0. [Complete route inventory](#0-complete-route-inventory)
1. [Authentication & headers](#1-authentication--headers)
2. [Shared JSON models](#2-shared-json-models)
3. [How to send data and read results](#3-how-to-send-data-and-read-results)
4. [Endpoint reference](#4-endpoint-reference)
5. [Errors](#5-errors)
6. [Live deployment, examples, and response detail](#6-live-deployment-examples-and-response-detail)
7. [Request and response by endpoint (PDF quick reference)](#7-request-and-response-by-endpoint-pdf-quick-reference)

---

## 0. Complete route inventory

### Application API (implemented in `azraq_mc/api.py`)

There are **20 HTTP operations** and **1 WebSocket** — **21** interfaces total.

| # | Method | Path | Summary |
|---|--------|------|---------|
| 1 | `GET` | `/health` | Liveness (no API key). |
| 2 | `GET` | `/v1/market/yfinance/{symbol}/history` | Yahoo OHLCV (query `period`). |
| 3 | `GET` | `/v1/market/yfinance/{symbol}/returns` | Yahoo simple returns. |
| 4 | `GET` | `/v1/market/ecb/eur-usd` | ECB EUR/USD spot. |
| 5 | `GET` | `/v1/calibration/stress-data-catalog` | Stress-source catalogue. |
| 6 | `GET` | `/v1/catalog/full-stack-factors` | 12-factor full-stack list. |
| 7 | `POST` | `/v1/calibration/preview` | Resolve `dynamic_margins` → `margins` (no MC). |
| 8 | `POST` | `/v1/simulate/scheduled/asset` | MC + optional snapshot file. |
| 9 | `POST` | `/v1/simulate/asset` | **Main** single-asset Monte Carlo. |
| 10 | `POST` | `/v1/simulate/v0/base-case` | Deterministic baseline (body = `AssetAssumptions`). |
| 11 | `POST` | `/v1/simulate/portfolio` | Joint MC, ≥2 assets. |
| 12 | `POST` | `/v1/shockpack/catalog/register` | Save shock pack → `entry_id`. |
| 13 | `POST` | `/v1/shockpack/catalog/{entry_id}/promote` | Change `promotion_tier`. |
| 14 | `GET` | `/v1/shockpack/catalog/{entry_id}` | Fetch catalogue row + `spec`. |
| 15 | `GET` | `/v1/shockpack/catalog` | List catalogue entries. |
| 16 | `POST` | `/v1/shockpack/export/npz` | Write shock `Z` to `.npz` on disk. |
| 17 | `POST` | `/v1/snapshots/save` | Save prior result JSON. |
| 18 | `GET` | `/v1/snapshots/list` | List snapshot paths. |
| 19 | `GET` | `/v1/audit/runs` | Recent audit rows (`limit`). |
| 20 | `POST` | `/v1/snapshots/diff/asset-metrics` | Diff two asset `SimulationResult` files. |
| 21 | `WebSocket` | `/ws/v1/simulate/portfolio` | Portfolio MC + optional progress. |

Anything not in this table is **not** a custom business route (see below).

### Also served (FastAPI + static UI)

These are automatic or mounted by the app, not separate “risk” APIs:

| Kind | Path | Purpose |
|------|------|---------|
| OpenAPI schema | `GET /openapi.json` | Machine-readable spec (codegen, Postman). |
| Swagger UI | `GET /docs` | Try-it-out browser UI. |
| ReDoc | `GET /redoc` | Alternate docs UI (if enabled by FastAPI defaults). |
| Static dashboard | `GET /app/…` | Investor UI (`frontend/`), only if that folder exists. |

---

## 1. Authentication & headers

| Condition | Client behaviour |
|-----------|-------------------|
| Server has **`AZRAQ_API_KEY`** set | Send header **`X-API-Key: <same value>`** on all routes **except** **`GET /health`** (health is public). |
| Optional audit | **`X-Azraq-User-Id`** — label stored with runs (not authentication). |
| Catalogue / tenant | **`X-Azraq-Tenant-Id`** — filters or enforces tenant on some **catalog** **`GET`** routes. |
| Promoting shock packs | **`POST /v1/shockpack/catalog/{entry_id}/promote`** needs **`X-Azraq-Catalog-Role`** in the allow-list (**`AZRAQ_CATALOG_PROMOTER_ROLES`**), unless that env is empty (local dev). |

**WebSocket:** if an API key is required, pass header **`x-api-key`** on the handshake (see portfolio WS below).

---

## 2. Shared JSON models

These names match **Pydantic / OpenAPI** schemas in the repo. Field-level detail: **`/docs`** or **[API.md](API.md)** § “Shared types”.

| Model | Used for |
|-------|-----------|
| **`FinancingAssumptions`** | `debt_principal`, `interest_rate_annual` (decimal), `loan_term_years`, `covenant_dscr` |
| **`AssetAssumptions`** | Project economics + `financing` + optional `utility_opex_annual`, `factor_transforms`, `full_stack`, … |
| **`ShockPackSpec`** | `shockpack_id`, `seed`, `n_scenarios`, `sampling_method`, `margins`, optional `dynamic_margins`, `correlation`, `factor_order`, … |
| **`AdhocSimulationRequest`** | `asset` + `shockpack` and/or `shockpack_catalog_entry_id` + optional attribution / `performance_profile` |
| **`ScheduledAssetRequest`** | Same as adhoc + `label`, `persist`, `model_version` |
| **`PortfolioSimulationRequest`** | `portfolio_id`, `portfolio_assumption_set_id`, `assets` (array, **≥ 2**), `shockpack` or catalogue id |
| **`SimulationResult`** | `metadata`, `metrics`, optional `attribution`, `full_stack`, `extensions` |
| **`BaseCaseResult`** | Deterministic run: `metadata`, `base` (point estimates) |
| **`PortfolioSimulationResult`** | `metadata`, `per_asset[]`, `portfolio` |
| **`CalibrationPreviewResponse`** | `resolved_shockpack`, `calibration_trace` |
| **`ScheduledAssetResponse`** | `result` (`SimulationResult`), `snapshot_path` |

Most JSON responses also include **`response_help`** (plain-language hints).

---

## 3. How to send data and read results

### Single-project Monte Carlo (typical integration)

1. **Build** an **`AssetAssumptions`** object from your systems (revenue, opex, capex, debt, rates, covenant, horizon, ids).
2. **Build** a **`ShockPackSpec`** (at least `shockpack_id`, `seed`, `n_scenarios`, `sampling_method`, and usually **`margins`** or **`dynamic_margins`** for calibration).
3. **POST** **`/v1/simulate/asset`** with body **`{ "asset": {...}, "shockpack": {...}, ... }`**.
4. **Read** **`200`** JSON **`SimulationResult`**: use **`metrics.dscr`**, **`metrics.irr_annual`**, **`metrics.covenant_breach_probability`**, tail fields, etc., and **`metadata`** for **`run_id`**, timing, seed.

**State:** there is **no session**. Each POST is independent. To “reset,” send a new body.

### Optional: validate calibration only (no MC)

**POST** **`/v1/calibration/preview`** with a full **`ShockPackSpec`** (e.g. with **`dynamic_margins.yahoo_finance`**). Response gives **`resolved_shockpack`** with concrete **`margins`** — paste that into simulate.

### Optional: save results for diffing

- **POST** **`/v1/simulate/scheduled/asset`** with **`persist: true`** → get **`snapshot_path`**.
- Or **POST** **`/v1/snapshots/save`** with a prior **`SimulationResult`** in **`result`**.

Then **POST** **`/v1/snapshots/diff/asset-metrics`** with **`before_path`** / **`after_path`**.

---

## 4. Endpoint reference

Legend: **Path** / **Query** / **Body** = where parameters go. **Auth** = needs **`X-API-Key`** when server key is set (except **`/health`**).

---

### `GET /health`

| | |
|--|--|
| **Purpose** | Liveness: server responds. |
| **Parameters** | None. |
| **Response** | `{ "status": "ok", "response_help": { ... } }` |
| **Usage** | Monitoring or pre-flight check. **No model run.** |
| **Auth** | None. |

---

### `GET /v1/market/yfinance/{symbol}/history`

| | |
|--|--|
| **Purpose** | Raw OHLCV history from Yahoo (inspection / reporting). |
| **Path** | **`symbol`** — ticker, e.g. `HG=F`. |
| **Query** | **`period`** — `1d`, `5d`, `1mo`, `3mo`, `6mo`, `1y`, `2y`, `5y`, `10y`, `ytd`, `max` (default `1y`). |
| **Response** | `{ "symbol", "period", "data": [ ... ] }` + **`response_help`**. **`404`** if no data; **`501`** if `yfinance` missing. |
| **Usage** | Does **not** run Monte Carlo. For feeding vol into the engine use **`dynamic_margins.yahoo_finance`** or **`/v1/calibration/preview`**. |
| **Auth** | Optional key. |

---

### `GET /v1/market/yfinance/{symbol}/returns`

| | |
|--|--|
| **Purpose** | Close-to-close **simple** returns series (human review). |
| **Path** | **`symbol`**. |
| **Query** | **`period`** — same set as history. |
| **Response** | `{ "symbol", "period", "returns": [{"date","return"},...], "n" }` + **`response_help`**. **`404`** / **`501`** as above. |
| **Usage** | Exploratory; internal calibration uses **log** returns + annualisation. |
| **Auth** | Optional key. |

---

### `GET /v1/market/ecb/eur-usd`

| | |
|--|--|
| **Purpose** | ECB daily **EUR/USD** reference from public XML. |
| **Parameters** | None. |
| **Response** | Rate fields + **`response_help`**. **`502`** if feed fails. |
| **Usage** | FX sanity checks; wire into **`dynamic_margins`** via your own JSON/file/http if needed. |
| **Auth** | Optional key. |

---

### `GET /v1/calibration/stress-data-catalog`

| | |
|--|--|
| **Purpose** | Catalogue of stress / data sources and integration hints (Appendix J–style). |
| **Parameters** | None. |
| **Response** | `{ "sources", "integration_overview", "response_help" }`. |
| **Usage** | Discover URLs and how they map to **`dynamic_margins`**. |
| **Auth** | Optional key. |

---

### `GET /v1/catalog/full-stack-factors`

| | |
|--|--|
| **Purpose** | Ordered **`factor_order`** + metadata for **12-factor full-stack** mode. |
| **Parameters** | None. |
| **Response** | `{ "factor_order", "risk_factors", "response_help" }`. |
| **Usage** | Required before **`asset.full_stack`** + matching 12-factor **`ShockPackSpec`**. |
| **Auth** | Optional key. |

---

### `POST /v1/calibration/preview`

| | |
|--|--|
| **Purpose** | Resolve **`dynamic_margins`** (file / http / Yahoo) into numeric **`margins`** **without** drawing scenarios. |
| **Body** | **`ShockPackSpec`** (JSON) — same shape as **`shockpack`** on simulate. |
| **Response** | **`CalibrationPreviewResponse`**: **`resolved_shockpack`**, **`calibration_trace`**. |
| **Usage** | Governance: confirm **`resolved_shockpack.margins`** before expensive **`/v1/simulate/asset`**. |
| **Auth** | Optional key. |

---

### `POST /v1/simulate/v0/base-case`

| | |
|--|--|
| **Purpose** | **Deterministic** single path (no random shocks). Fast tie-out vs spreadsheet. |
| **Body** | **`AssetAssumptions`** as **root** JSON (not wrapped in `{ "asset": ... }`). |
| **Response** | **`BaseCaseResult`**: **`metadata`** (`execution_mode: "v0_base"`), **`base`** point estimates (`dscr`, `irr_annual`, …). |
| **Usage** | Baseline only — **not** tail risk. |
| **Auth** | Optional key. |

---

### `POST /v1/simulate/asset`

| | |
|--|--|
| **Purpose** | Main **Monte Carlo** for **one** asset — DSCR/IRR distributions, breach probability, etc. |
| **Body** | **`AdhocSimulationRequest`**: **`asset`** (required); **`shockpack`** and/or **`shockpack_catalog_entry_id`**; optional **`include_attribution`**, **`include_advanced_attribution`**, **`attribution_tail_fraction`**, **`performance_profile`**. |
| **Response** | **`SimulationResult`**: **`metadata`**, **`metrics`**, optional **`attribution`**, **`full_stack`**, **`extensions`**. |
| **Usage** | Primary integration: **send** economics + shock spec, **receive** **`metrics`** for dashboards or storage. |
| **Auth** | Optional key. |

---

### `POST /v1/simulate/scheduled/asset`

| | |
|--|--|
| **Purpose** | Same maths as **`/v1/simulate/asset`**, optional **on-disk JSON snapshot** for monitoring / diff. |
| **Body** | **`ScheduledAssetRequest`**: all **`AdhocSimulationRequest`** fields + **`label`**, **`persist`** (default true), **`model_version`**. |
| **Response** | **`ScheduledAssetResponse`**: **`result`** (`SimulationResult`), **`snapshot_path`** or `null`. |
| **Usage** | Recurring runs; pair with **`/v1/snapshots/diff/asset-metrics`**. Snapshot root: **`AZRAQ_SNAPSHOT_DIR`** or default `data/snapshots`. |
| **Auth** | Optional key. |

---

### `POST /v1/simulate/portfolio`

| | |
|--|--|
| **Purpose** | **Joint** Monte Carlo for **≥ 2** assets (same shock draw per scenario across names). |
| **Body** | **`PortfolioSimulationRequest`**: **`shockpack`** or catalogue id; **`portfolio_id`**, **`portfolio_assumption_set_id`**, **`assets`** (array length ≥ 2); optional **`performance_profile`**. |
| **Response** | **`PortfolioSimulationResult`**: **`metadata`**, **`per_asset`**, **`portfolio`** (e.g. **`probability_any_covenant_breach`**, **`min_dscr_across_assets`**). |
| **Usage** | Portfolio concentration; joint breach ≠ sum of silo runs. |
| **Auth** | Optional key. |

---

### `WebSocket` `WS /ws/v1/simulate/portfolio`

| | |
|--|--|
| **Purpose** | Same as **`POST /v1/simulate/portfolio`** with optional **progress** messages. |
| **Handshake** | If **`AZRAQ_API_KEY`** set: header **`x-api-key`**. |
| **Messages** | Client sends **one** JSON = **`PortfolioSimulationRequest`**. Server: optional `{ "type":"progress", ... }`, then `{ "type":"result", "body": <PortfolioSimulationResult> }` or `{ "type":"error", "detail" }`. |
| **Usage** | Long runs from browser / clients that prefer streaming. |
| **Auth** | **`x-api-key`** when server key is set. |

---

### `POST /v1/shockpack/catalog/register`

| | |
|--|--|
| **Purpose** | Store a **`ShockPackSpec`** in the catalogue for reuse. |
| **Body** | **`ShockPackSpec`** (JSON). |
| **Query** | **`semver`** (default `1.0.0`), optional **`tenant_id`**, **`promotion_tier`** (`dev`/`staging`/`prod`), **`rbac_owner_role`**. |
| **Response** | `{ "entry_id": "<uuid>", "response_help": ... }` — use **`entry_id`** as **`shockpack_catalog_entry_id`** on simulate. |
| **Usage** | Freeze governance-approved shock design; inline **`shockpack`** can still patch fields. |
| **Auth** | Optional key. |

---

### `POST /v1/shockpack/catalog/{entry_id}/promote`

| | |
|--|--|
| **Purpose** | Change catalogue **`promotion_tier`** (e.g. dev → prod). |
| **Path** | **`entry_id`**. |
| **Query** | **`to_tier`** — `dev` \| `staging` \| `prod`. |
| **Headers** | **`X-Azraq-Catalog-Role`** unless promoter env list is empty. |
| **Response** | `{ "ok": true, "response_help": ... }` — **`403`** if role not allowed. |
| **Usage** | Gate “approved” packs in **`GET /v1/shockpack/catalog?promotion_tier=prod`**. |
| **Auth** | Optional key + promoter role. |

---

### `GET /v1/shockpack/catalog/{entry_id}`

| | |
|--|--|
| **Purpose** | Fetch one catalogue row including full **`spec`**. |
| **Path** | **`entry_id`**. |
| **Headers** | Optional **`X-Azraq-Tenant-Id`** — must match entry tenant if enforced. |
| **Response** | Catalogue object + **`response_help`**. **`403`** tenant mismatch; **`404`** missing. |
| **Usage** | Inspect exact shock JSON before production runs. |
| **Auth** | Optional key. |

---

### `GET /v1/shockpack/catalog`

| | |
|--|--|
| **Purpose** | List recent registrations (**metadata**; use **GET by id** for full **`spec`**). |
| **Query** | **`limit`** (default 100), optional **`tenant_id`**, **`promotion_tier`**. Header tenant may filter. |
| **Response** | `{ "entries": [ ... ], "response_help": ... }`. |
| **Usage** | Discover **`entry_id`** for CI/CD. |
| **Auth** | Optional key. |

---

### `POST /v1/shockpack/export/npz`

| | |
|--|--|
| **Purpose** | Write correlated shock array **`Z`** to a **`.npz`** file on the server (offline HPC / custom models). |
| **Body** | **`ShockExportRequest`**: **`shockpack`** (required), optional **`directory`**. |
| **Response** | `{ "path": "<absolute .npz path>", "response_help": ... }`. **`dynamic_margins`** resolved before draw. |
| **Usage** | No DSCR/IRR — only random draws. Default dir: **`AZRAQ_SHOCK_EXPORT_DIR`** or `data/shockpacks`. |
| **Auth** | Optional key. |

---

### `POST /v1/snapshots/save`

| | |
|--|--|
| **Purpose** | Persist an **already computed** result to JSON on disk. |
| **Body** | **`SnapshotSaveRequest`**: optional **`label`**, **`result`** = full **`SimulationResult`** / **`PortfolioSimulationResult`** / **`BaseCaseResult`**. |
| **Response** | `{ "path": "<absolute path>", "response_help": ... }`. |
| **Usage** | Bookmark or feed external tools; same root as scheduled snapshots. |
| **Auth** | Optional key. |

---

### `GET /v1/snapshots/list`

| | |
|--|--|
| **Purpose** | List snapshot **file paths** under the snapshot root. |
| **Parameters** | None. |
| **Response** | `{ "paths": [ "..." ], "response_help": ... }`. |
| **Usage** | Pick **`before_path`** / **`after_path`** for diff. |
| **Auth** | Optional key. |

---

### `POST /v1/snapshots/diff/asset-metrics`

| | |
|--|--|
| **Purpose** | Compare two **saved** asset **`SimulationResult`** snapshots. |
| **Body** | `{ "before_path": "<server path>", "after_path": "<server path>" }`. |
| **Response** | **`metrics_delta`**, **`provenance_delta`**, **`response_help`**. |
| **Usage** | Explain drift: assumptions vs shock vs seed vs model version. **`400`** if either file is not an asset MC result. |
| **Auth** | Optional key. |

---

### `GET /v1/audit/runs`

| | |
|--|--|
| **Purpose** | Recent simulation events from SQLite audit DB (if enabled). |
| **Query** | **`limit`** (default 50). |
| **Response** | `{ "runs": [ { "run_id", "run_kind", "asset_id", "shockpack_id", "seed", "n_scenarios", ... } ], "response_help": ... }`. |
| **Usage** | Correlate **`run_id`** with **`SimulationResult.metadata.run_id`**. Empty if audit disabled/missing. |
| **Auth** | Optional key. |

---

## 5. Errors

| HTTP | Typical cause |
|------|----------------|
| **401** | Missing or wrong **`X-API-Key`** when server requires it. |
| **403** | Catalogue tenant / promoter role mismatch. |
| **404** | Yahoo history missing; unknown catalogue **`entry_id`**. |
| **400** | Validation: bad JSON shape, wrong asset count for portfolio, wrong snapshot types for diff. |
| **422** | Pydantic validation detail (FastAPI) — check **`detail`** array for field paths. |
| **501** | Optional dependency missing (e.g. **`yfinance`**). |
| **502** | Upstream feed failure (e.g. ECB). |

For **`422`**, use **`/docs`** “Try it out” or client validation against **`/openapi.json`** to align payloads before production.

---

## 7. Request and response by endpoint (PDF quick reference)

This section lists **concrete request placement** (path, query, headers, body schema) and a **representative `200` JSON** shape for each application route. Optional fields are often omitted in examples; **`response_help`** is shortened to `{}` where it would repeat. Full nested models: **[Swagger UI](https://monte-carlo.octaloop.dev/docs#/)** or **`GET /openapi.json`**. Error statuses (401, 403, 404, …) match **[§5 Errors](#5-errors)**.

### 7.1 `GET /health`

| Request | None (no body, no API key). |
| **Response `200`** | `application/json` |

```json
{
  "status": "ok",
  "response_help": {}
}
```

### 7.2 `GET /v1/market/yfinance/{symbol}/history`

| Request | Path **`symbol`** (e.g. `HG=F`). Query **`period`** (default `1y`). Optional **`X-API-Key`**. |
| **Response `200`** | Yahoo OHLCV rows in **`data`** (column names from the provider export). |

```json
{
  "symbol": "HG=F",
  "period": "1y",
  "data": [
    {
      "Date": "2024-01-02",
      "Open": 3.85,
      "High": 3.9,
      "Low": 3.8,
      "Close": 3.88,
      "Volume": 12345
    }
  ],
  "response_help": {}
}
```

### 7.3 `GET /v1/market/yfinance/{symbol}/returns`

| Request | Same path/query/headers as **§7.2**. |
| **Response `200`** | Simple close-to-close returns. |

```json
{
  "symbol": "HG=F",
  "period": "1y",
  "returns": [{ "date": "2024-01-03", "return": 0.0012 }],
  "n": 250,
  "response_help": {}
}
```

### 7.4 `GET /v1/market/ecb/eur-usd`

| Request | Optional **`X-API-Key`**. |
| **Response `200`** | Latest daily ECB reference (**1 EUR = `one_eur_in_usd` USD**). |

```json
{
  "source": "ecb",
  "source_url": "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml",
  "rate_date": "2024-04-05",
  "quote": "EUR/USD",
  "one_eur_in_usd": 1.08,
  "response_help": {}
}
```

### 7.5 `GET /v1/calibration/stress-data-catalog`

| Request | Optional **`X-API-Key`**. |
| **Response `200`** | Stress-source list + integration hints. |

```json
{
  "sources": [{ "id": "copper", "label": "LME / copper proxy", "notes": "…" }],
  "integration_overview": { "dynamic_margins": "Use with ShockPackSpec.dynamic_margins" },
  "response_help": {}
}
```

### 7.6 `GET /v1/catalog/full-stack-factors`

| Request | Optional **`X-API-Key`**. |
| **Response `200`** | Factor order + catalog entries for 12-factor **`full_stack`** mode. |

```json
{
  "factor_order": ["infra_delivery", "thermal", "…"],
  "risk_factors": [{ "key": "infra_delivery", "description": "…" }],
  "response_help": {}
}
```

### 7.7 `POST /v1/calibration/preview`

| Request | Body **`ShockPackSpec`** (same JSON as simulate **`shockpack`**). Optional **`X-API-Key`**. |
| **Response `200`** | **`CalibrationPreviewResponse`** — resolved numeric **`margins`**, optional **`calibration_trace`**. |

```json
{
  "resolved_shockpack": {
    "shockpack_id": "demo",
    "schema_version": "1.0",
    "seed": 42,
    "n_scenarios": 5000,
    "sampling_method": "monte_carlo",
    "factor_order": ["revenue", "capex", "opex", "rate"],
    "correlation": [
      [1.0, 0.35, 0.25, 0.15],
      [0.35, 1.0, 0.45, 0.1],
      [0.25, 0.45, 1.0, 0.05],
      [0.15, 0.1, 0.05, 1.0]
    ],
    "margins": {
      "revenue_log_mean": 0,
      "revenue_log_sigma": 0.08,
      "capex_log_mean": 0,
      "capex_log_sigma": 0.06,
      "opex_log_mean": 0,
      "opex_log_sigma": 0.05,
      "rate_shock_sigma": 0.005
    },
    "dynamic_margins": null,
    "copula": "gaussian",
    "t_degrees_freedom": 8,
    "macro_regime": "baseline"
  },
  "calibration_trace": { "sources_applied": [] },
  "response_help": {}
}
```

### 7.8 `POST /v1/simulate/scheduled/asset`

| Request | Body **`ScheduledAssetRequest`** (`**`AdhocSimulationRequest`**` fields plus **`label`**, **`persist`**, **`model_version`**). Optional **`X-API-Key`**, **`X-Azraq-User-Id`**. |
| **Response `200`** | **`ScheduledAssetResponse`**: full **`SimulationResult`** in **`result`**, optional **`snapshot_path`**. |

```json
{
  "result": {
    "metadata": {
      "run_id": "9b1e5c2a-…",
      "shockpack_id": "demo-sp-1",
      "assumption_set_id": "as-1",
      "asset_id": "asset-1",
      "model_version": "azraq-mc-v1",
      "seed": 42,
      "n_scenarios": 800,
      "sampling_method": "monte_carlo",
      "created_at_utc": "2026-04-07T12:00:00+00:00",
      "execution_mode": "scheduled_monitoring",
      "compute_time_ms": 1234.5
    },
    "metrics": {
      "dscr": {
        "p05": 1.0,
        "p10": 1.1,
        "p50": 1.35,
        "p90": 1.6,
        "p95": 1.7,
        "mean": 1.36,
        "std": 0.12
      },
      "irr_annual": {
        "p05": 0.02,
        "p10": 0.04,
        "p50": 0.08,
        "p90": 0.12,
        "p95": 0.14,
        "mean": 0.08,
        "std": 0.03
      },
      "covenant_breach_probability": 0.08,
      "probability_of_default_proxy_dscr_lt_1": 0.02
    },
    "response_help": {}
  },
  "snapshot_path": "E:/data/snapshots/asset_simulation_… .json",
  "response_help": {}
}
```

### 7.9 `POST /v1/simulate/asset`

| Request | Body **`AdhocSimulationRequest`** (see **[§6.2](#62-adhocsimulationrequest--request-fields-main-monte-carlo)**). Optional **`X-API-Key`**, **`X-Azraq-User-Id`**. |
| **Response `200`** | **`SimulationResult`**: **`metadata`**, **`metrics`**, optional **`attribution`**, **`full_stack`**, **`extensions`**. |

```json
{
  "metadata": {
    "run_id": "…",
    "shockpack_id": "demo-sp-1",
    "assumption_set_id": "as-1",
    "asset_id": "asset-1",
    "model_version": "azraq-mc-v1",
    "seed": 42,
    "n_scenarios": 800,
    "sampling_method": "monte_carlo",
    "execution_mode": "adhoc_asset"
  },
  "metrics": {
    "dscr": {
      "p05": 1.0,
      "p10": 1.1,
      "p50": 1.35,
      "p90": 1.6,
      "p95": 1.7,
      "mean": 1.36,
      "std": 0.12
    },
    "irr_annual": {
      "p05": 0.02,
      "p10": 0.04,
      "p50": 0.08,
      "p90": 0.12,
      "p95": 0.14,
      "mean": 0.08,
      "std": 0.03
    },
    "covenant_breach_probability": 0.08
  },
  "response_help": {}
}
```

*(Additional metric keys: **[§6.3](#63-simulationresultmetrics--main-outputs-read-after-post-v1simulateasset)**.)*

### 7.10 `POST /v1/simulate/v0/base-case`

| Request | Root body **`AssetAssumptions`** only (not wrapped in **`asset`**). Optional **`X-API-Key`**, **`X-Azraq-User-Id`**. |
| **Response `200`** | **`BaseCaseResult`**: **`metadata`** + deterministic **`base`** block. |

```json
{
  "metadata": {
    "run_id": "…",
    "shockpack_id": "v0-deterministic",
    "assumption_set_id": "as-1",
    "asset_id": "demo",
    "model_version": "azraq-mc-v1",
    "seed": 0,
    "n_scenarios": 1,
    "sampling_method": "monte_carlo",
    "execution_mode": "v0_base"
  },
  "base": {
    "dscr": 1.35,
    "irr_annual": 0.082,
    "annual_revenue": 12000000,
    "ebitda": 6500000,
    "debt_service": 4800000,
    "initial_equity": 28000000,
    "utility_opex_exposure": 0,
    "revenue_multiplier": 1.0,
    "capex_multiplier": 1.0,
    "opex_multiplier": 1.0,
    "effective_interest_rate": 0.055,
    "npv_equity": null,
    "enterprise_value": null
  },
  "response_help": {}
}
```

### 7.11 `POST /v1/simulate/portfolio`

| Request | Body **`PortfolioSimulationRequest`** — at least two **`assets`**, plus **`shockpack`** and/or **`shockpack_catalog_entry_id`**, **`portfolio_id`**, **`portfolio_assumption_set_id`**. Optional **`performance_profile`**, **`X-API-Key`**, **`X-Azraq-User-Id`**. |

```json
{
  "portfolio_id": "pf-1",
  "portfolio_assumption_set_id": "pas-1",
  "assets": [
    {
      "asset_id": "a1",
      "assumption_set_id": "as-1",
      "horizon_years": 8,
      "base_revenue_annual": 12000000,
      "base_opex_annual": 5000000,
      "initial_capex": 80000000,
      "equity_fraction": 0.35,
      "tax_rate": 0,
      "financing": {
        "debt_principal": 40000000,
        "interest_rate_annual": 0.055,
        "loan_term_years": 12,
        "covenant_dscr": 1.2
      }
    },
    {
      "asset_id": "a2",
      "assumption_set_id": "as-2",
      "horizon_years": 8,
      "base_revenue_annual": 8000000,
      "base_opex_annual": 3000000,
      "initial_capex": 50000000,
      "equity_fraction": 0.4,
      "tax_rate": 0,
      "financing": {
        "debt_principal": 25000000,
        "interest_rate_annual": 0.055,
        "loan_term_years": 10,
        "covenant_dscr": 1.15
      }
    }
  ],
  "shockpack": {
    "shockpack_id": "pf-sp",
    "seed": 7,
    "n_scenarios": 2000,
    "sampling_method": "monte_carlo"
  }
}
```

| **Response `200`** | **`PortfolioSimulationResult`**: **`metadata`**, **`per_asset[]`**, **`portfolio`**. |

```json
{
  "metadata": {
    "run_id": "…",
    "portfolio_id": "pf-1",
    "assumption_set_id": "pas-1",
    "shockpack_id": "pf-sp",
    "model_version": "azraq-mc-v1",
    "seed": 7,
    "n_scenarios": 2000,
    "sampling_method": "monte_carlo",
    "asset_ids": ["a1", "a2"],
    "execution_mode": "portfolio_joint",
    "compute_time_ms": 5000
  },
  "per_asset": [
    {
      "asset_id": "a1",
      "assumption_set_id": "as-1",
      "metrics": {
        "dscr": {
          "p05": 1.0,
          "p10": 1.05,
          "p50": 1.3,
          "p90": 1.55,
          "p95": 1.65,
          "mean": 1.3,
          "std": 0.1
        },
        "irr_annual": null,
        "covenant_breach_probability": 0.05
      }
    }
  ],
  "portfolio": {
    "n_assets": 2,
    "scenarios": 2000,
    "probability_any_covenant_breach": 0.12,
    "probability_at_least_k_breaches": {},
    "min_dscr_across_assets": {
      "p05": 0.95,
      "p10": 1.0,
      "p50": 1.2,
      "p90": 1.45,
      "p95": 1.55,
      "mean": 1.2,
      "std": 0.11
    },
    "sum_levered_cf_year1": {
      "p05": 1000000,
      "p10": 1200000,
      "p50": 2000000,
      "p90": 2800000,
      "p95": 3000000,
      "mean": 2000000,
      "std": 500000
    }
  },
  "response_help": {}
}
```

### 7.12 `POST /v1/shockpack/catalog/register`

| Request | Body **`ShockPackSpec`**. Query **`semver`**, **`tenant_id`**, **`promotion_tier`**, **`rbac_owner_role`**. |
| **Response `200`** | New catalogue **`entry_id`**. |

```json
{
  "entry_id": "550e8400-e29b-41d4-a716-446655440000",
  "response_help": {}
}
```

### 7.13 `POST /v1/shockpack/catalog/{entry_id}/promote`

| Request | Path **`entry_id`**. Query **`to_tier`**: `dev` | `staging` | `prod`. Header **`X-Azraq-Catalog-Role`** when promoter allow-list is configured. |
| **Response `200`** | Acknowledgement. |

```json
{ "ok": true, "response_help": {} }
```

### 7.14 `GET /v1/shockpack/catalog/{entry_id}`

| Request | Path **`entry_id`**. Optional **`X-Azraq-Tenant-Id`** (must match stored tenant if enforced). |
| **Response `200`** | Row + full **`spec`** (`**`ShockPackSpec`**`). |

```json
{
  "entry_id": "550e8400-e29b-41d4-a716-446655440000",
  "shockpack_id": "demo",
  "semver": "1.0.0",
  "tenant_id": null,
  "spec": {
    "shockpack_id": "demo",
    "seed": 42,
    "n_scenarios": 5000,
    "sampling_method": "monte_carlo"
  },
  "signature": "…",
  "created_at_utc": "2026-04-07T12:00:00",
  "macro_regime": "baseline",
  "promotion_tier": "dev",
  "content_sha256": "…",
  "object_uri": null,
  "rbac_owner_role": "editor",
  "response_help": {}
}
```

### 7.15 `GET /v1/shockpack/catalog`

| Request | Query **`limit`**, **`tenant_id`**, **`promotion_tier`**. Header tenant may filter. |
| **Response `200`** | Metadata list (no full **`spec`** here — use **§7.14**). |

```json
{
  "entries": [
    {
      "entry_id": "…",
      "shockpack_id": "demo",
      "semver": "1.0.0",
      "tenant_id": null,
      "created_at_utc": "2026-04-07T12:00:00",
      "macro_regime": "baseline",
      "promotion_tier": "dev",
      "content_sha256": "…"
    }
  ],
  "response_help": {}
}
```

### 7.16 `POST /v1/shockpack/export/npz`

| Request | Body **`ShockExportRequest`**: **`shockpack`** (required), optional **`directory`**. |
| **Response `200`** | Absolute path to written **`.npz`**. |

```json
{
  "path": "E:/data/shockpacks/demo_….npz",
  "response_help": {}
}
```

### 7.17 `POST /v1/snapshots/save`

| Request | Body **`SnapshotSaveRequest`**: optional **`label`**, **`result`** = full **`SimulationResult`**, **`PortfolioSimulationResult`**, or **`BaseCaseResult`**. |
| **Response `200`** | Path to saved snapshot JSON. |

```json
{
  "path": "E:/data/snapshots/asset_simulation_….json",
  "response_help": {}
}
```

### 7.18 `GET /v1/snapshots/list`

| Request | Optional **`X-API-Key`**. |
| **Response `200`** | Absolute paths of **`*.json`** under the snapshot root. |

```json
{
  "paths": [
    "E:/data/snapshots/asset_simulation_20260407T120000Z_run.json"
  ],
  "response_help": {}
}
```

### 7.19 `POST /v1/snapshots/diff/asset-metrics`

| Request | Body **`{ "before_path": "<server path>", "after_path": "<server path>" }`** — both must be **`asset_simulation`** snapshots. |
| **Response `200`** | **`metrics_delta`**: flattened keys like **`dscr.mean`** with **`before`**, **`after`**, **`delta`**. **`provenance_delta`**: booleans and metadata deltas. |

```json
{
  "metrics_delta": {
    "dscr.mean": { "before": 1.36, "after": 1.28, "delta": -0.08 },
    "covenant_breach_probability": { "before": 0.06, "after": 0.1, "delta": 0.04 }
  },
  "provenance_delta": {
    "asset_id_changed": false,
    "assumption_set_changed": false,
    "shockpack_id_changed": true,
    "seed_changed": false,
    "n_scenarios_changed": false,
    "sampling_method_changed": false,
    "model_version_changed": false,
    "layer_versions_delta": {},
    "catalog_entry": { "before": null, "after": "550e8400-…" },
    "performance_profile": { "before": null, "after": "standard" }
  },
  "response_help": {}
}
```

### 7.20 `GET /v1/audit/runs`

| Request | Query **`limit`** (default 50). |
| **Response `200`** | Recent audit rows (empty **`runs`** if DB missing/disabled). |

```json
{
  "runs": [
    {
      "run_id": "9b1e5c2a-…",
      "run_kind": "adhoc_asset",
      "asset_id": "asset-1",
      "portfolio_id": null,
      "shockpack_id": "demo-sp-1",
      "assumption_set_id": "as-1",
      "seed": 42,
      "n_scenarios": 800,
      "created_at_utc": "2026-04-07T12:00:00+00:00",
      "client_hint": "http:asset"
    }
  ],
  "response_help": {}
}
```

### 7.21 WebSocket `WS /ws/v1/simulate/portfolio`

| **Handshake** | If **`AZRAQ_API_KEY`** is set: header **`x-api-key`**. |
| **Client message** | **One** JSON object: same body as **`POST /v1/simulate/portfolio`** (**`PortfolioSimulationRequest`**). |
| **Server messages** | **`{ "type": "progress", "done": <int>, "of": <int> }`** (zero or more). Then **`{ "type": "result", "body": <PortfolioSimulationResult JSON> }`** on success, or **`{ "type": "error", "detail": "<message>" }`**. |

Example success tail:

```json
{
  "type": "result",
  "body": {
    "metadata": { "run_id": "…", "portfolio_id": "pf-1" },
    "per_asset": [],
    "portfolio": { "n_assets": 2, "scenarios": 2000 },
    "response_help": {}
  }
}
```

---

## 6. Live deployment, examples, and response detail

### 6.1 Public host (Octaloop)

| Resource | URL |
|----------|-----|
| **Swagger UI** (schemas + “Try it out”) | [https://monte-carlo.octaloop.dev/docs#/](https://monte-carlo.octaloop.dev/docs#/) |
| **OpenAPI JSON** (import to Postman, codegen) | `https://monte-carlo.octaloop.dev/openapi.json` |
| **Web app** (if deployed) | `https://monte-carlo.octaloop.dev/app/` |

Use **`https://monte-carlo.octaloop.dev`** as the host for the paths in §4 (e.g. `POST https://monte-carlo.octaloop.dev/v1/simulate/asset`). If the server has **`AZRAQ_API_KEY`** set, add header **`X-API-Key`** on calls other than **`GET /health`**.

### 6.2 `AdhocSimulationRequest` — request fields (main Monte Carlo)

| Field | Required | Type / notes |
|-------|----------|----------------|
| `asset` | Yes | Full **`AssetAssumptions`** (ids, horizon, revenue, opex, capex, equity, financing, optional `utility_opex_annual`, `factor_transforms`, `full_stack`, …). |
| `shockpack` | One of pack or catalogue | Inline **`ShockPackSpec`** (`shockpack_id`, `seed`, `n_scenarios`, `sampling_method`, `margins`, optional `dynamic_margins`, `correlation`, …). |
| `shockpack_catalog_entry_id` | One of pack or catalogue | UUID from **`POST /v1/shockpack/catalog/register`**; inline `shockpack` can patch fields. |
| `include_attribution` | No | Default `false`. Tail attribution (indicative narrative). |
| `include_advanced_attribution` | No | Default `false`. Extra factor weights when attribution on. |
| `attribution_tail_fraction` | No | Default `0.05` (e.g. worst ~5% scenarios for attribution). |
| `performance_profile` | No | `"interactive"` (caps **`n_scenarios`**, good for UI), `"standard"`, `"deep"` (no cap), or `null`. |

### 6.3 `SimulationResult.metrics` — main outputs (read after `POST /v1/simulate/asset`)

| Field | Meaning |
|-------|---------|
| `dscr` | **`DistributionSummary`**: percentiles (e.g. `p05`–`p95`), `mean`, `std` — debt service coverage over the run. |
| `irr_annual` | **`DistributionSummary`** for equity IRR (decimal per year, e.g. `0.08` = 8%). |
| `total_capex` | Optional **`DistributionSummary`** for stochastic nominal build cost when the engine supplies it. |
| `covenant_breach_probability` | Share of paths where modeled DSCR falls below **`asset.financing.covenant_dscr`**. |
| `probability_of_default_proxy_dscr_lt_1` | PD-style proxy using DSCR &lt; 1 (see OpenAPI / product definition). |
| `var_irr_95` / `cvar_irr_95` | Tail / shortfall style metrics on IRR when populated. |
| `ebitda`, `levered_cf`, `nav_proxy_equity`, … | Other **`DistributionSummary`** blocks when enabled by model path. |

Always read **`metadata`** for **`run_id`**, **`seed`**, **`n_scenarios`**, **`compute_time_ms`**, **`shockpack_id`**, optional **`margin_calibration_trace`** (if Yahoo/file/http calibration ran).

### 6.4 Example: health check (no API key)

Replace `HOST` with `https://monte-carlo.octaloop.dev` or `http://127.0.0.1:8000`.

```
curl -sS "${HOST}/health"
```

### 6.5 Example: single-asset Monte Carlo (minimal body)

Send **`Content-Type: application/json`**. If an API key is required, add `-H "X-API-Key: YOUR_KEY"`.

```
curl -sS -X POST "${HOST}/v1/simulate/asset" \
  -H "Content-Type: application/json" \
  -d '{
    "shockpack": {
      "shockpack_id": "demo-sp-1",
      "seed": 42,
      "n_scenarios": 800,
      "sampling_method": "monte_carlo",
      "margins": {
        "revenue_log_mean": 0,
        "revenue_log_sigma": 0.08,
        "capex_log_mean": 0,
        "capex_log_sigma": 0.06,
        "opex_log_mean": 0,
        "opex_log_sigma": 0.05,
        "rate_shock_sigma": 0.005
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
    "include_attribution": false,
    "performance_profile": "interactive"
  }'
```

**Note:** The JSON above uses a fully specified **`margins`** block. If **`dynamic_margins`** (Yahoo/file/http) is used instead, run **`POST /v1/calibration/preview`** first to validate resolved sigmas. Omit **`performance_profile`** or use `"standard"` / `"deep"` for higher scenario limits (see OpenAPI).

### 6.6 Example: deterministic baseline (no Monte Carlo)

Body is **`AssetAssumptions`** only (not wrapped in `asset`).

```
curl -sS -X POST "${HOST}/v1/simulate/v0/base-case" \
  -H "Content-Type: application/json" \
  -d '{"asset_id":"demo","assumption_set_id":"v0","horizon_years":8,
       "base_revenue_annual":12000000,"base_opex_annual":5000000,
       "initial_capex":80000000,"equity_fraction":0.35,"tax_rate":0,
       "financing":{"debt_principal":40000000,"interest_rate_annual":0.055,
       "loan_term_years":12,"covenant_dscr":1.2}}'
```

### 6.7 WebSocket portfolio run

Connect to `wss://monte-carlo.octaloop.dev/ws/v1/simulate/portfolio` (or `ws://127.0.0.1:8000/...` locally). Send **one** message: same JSON as **`POST /v1/simulate/portfolio`**. If API key is set, send header **`x-api-key`** on the handshake.

### 6.8 Where to see every field

Open **[Swagger UI](https://monte-carlo.octaloop.dev/docs#/)**, expand **`POST /v1/simulate/asset`**, inspect **Request body** and **Response** schemas (`AdhocSimulationRequest`, `SimulationResult`, `FinancialRiskMetrics`, …). The PDF cannot replace the live schema explorer for nested optional fields.

---

## Related documents

| File | Role |
|------|------|
| **[API.md](API.md)** | Full narrative, examples, **`response_help`**, security notes |
| **[INTEGRATION.md](INTEGRATION.md)** | Minimal request, mapping checklist, stateless “reset” |
| **[PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)** | Product-level engine description |
| **`Azraq_Monte_Carlo_API_Reference.pdf`** | Print-ready PDF of this reference (`python scripts/build_api_reference_pdf.py`) |
