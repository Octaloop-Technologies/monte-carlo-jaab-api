# API endpoints reference

One section per route: **what it does**, **what you send**, **what you get**.

**Base URL (local):** `http://127.0.0.1:8000`  
**OpenAPI / Try it:** `http://127.0.0.1:8000/docs`

**Full numbered list (21 routes) + `/docs`, `/openapi.json`, `/app`:** see **[ENDPOINTS.md](ENDPOINTS.md) § Complete route inventory** — this file uses the same **21** application endpoints in narrative tables below (not “13–14”; count the `## \` headings through WebSocket).

## Authentication and headers

| Item | When |
|------|------|
| **`AZRAQ_API_KEY`** in `.env` | If set, all routes below **except** `GET /health` expect header **`X-API-Key: <same value>`**. |
| **`X-Azraq-User-Id`** | Optional label stored on audited runs (not login). |
| **`X-Azraq-Tenant-Id`** | Optional. Filters `GET /v1/shockpack/catalog` and must match stored tenant on `GET /v1/shockpack/catalog/{entry_id}` when the entry is tenant-scoped. |
| **`X-Azraq-Catalog-Role`** | Required for `POST /v1/shockpack/catalog/{entry_id}/promote` unless `AZRAQ_CATALOG_PROMOTER_ROLES` is empty (typical local dev). Value must be in that allow-list (default includes `admin`, `promoter`). |

Many JSON responses include **`response_help`**: plain-language `what_you_sent`, `what_you_received`, `findings_and_next_steps`, and sometimes `glossary`.

---

## `GET /health`

| | |
|---|---|
| **What it does** | Liveness check: confirms the HTTP process responds. Does **not** run the financial model or touch the database. |
| **What you send** | No body. **No API key** (always public). |
| **What you get (200)** | `{ "status": "ok", "response_help": { ... } }`. |
| **Errors** | Connection failure if the server is down (no JSON). |

---

## `GET /v1/market/yfinance/{symbol}/history`

| | |
|---|---|
| **What it does** | Returns **OHLCV history** from Yahoo Finance for inspection (e.g. copper `HG=F`). Not a simulation. |
| **What you send** | Path: **`symbol`** (e.g. `HG=F`, `^GSPC`). Query: **`period`** — `1d`, `5d`, `1mo`, `3mo`, `6mo`, `1y`, `2y`, `5y`, `10y`, `ytd`, `max` (default `1y`). Optional `X-API-Key` if configured. |
| **What you get (200)** | `{ "symbol", "period", "data": [ { "Date", "Open", "High", "Low", "Close", "Volume", ... }, ... ], "response_help" }`. |
| **Errors** | **404** — no Yahoo series for that symbol/period. **501** — `yfinance` not installed. **401** — missing/invalid API key when required. |

---

## `GET /v1/market/yfinance/{symbol}/returns`

| | |
|---|---|
| **What it does** | **Simple** close-to-close daily returns for intuition (volatility eyeball). Internal Yahoo calibration uses **log** returns and its own annualisation. |
| **What you send** | Path **`symbol`**, query **`period`** (same set as history). Optional `X-API-Key`. |
| **What you get (200)** | `{ "symbol", "period", "returns": [ { "date", "return" }, ... ], "n", "response_help" }`. |
| **Errors** | **404** / **501** / **401** as for history. |

---

## `GET /v1/market/ecb/eur-usd`

| | |
|---|---|
| **What it does** | Fetches **ECB daily** EUR/USD reference from public XML (not Yahoo). |
| **What you send** | Nothing. Optional `X-API-Key`. |
| **What you get (200)** | `{ "source": "ecb", "source_url", "rate_date", "quote", "one_eur_in_usd", "response_help" }`. |
| **Errors** | **502** — fetch/parse failure. **401** when API key required. |

---

## `GET /v1/calibration/stress-data-catalog`

| | |
|---|---|
| **What it does** | **Appendix J–style** catalogue: stress drivers, example URLs, tiers, hints for `dynamic_margins` / full-stack factors. |
| **What you send** | Nothing. Optional `X-API-Key`. |
| **What you get (200)** | `{ "sources": [ { "id", "category", "macro_metric", "engine_integration_note", "integration_paths", "typical_engine_hooks", ... }, ... ], "integration_overview": { ... }, "response_help" }`. |
| **Errors** | **401** when API key required. |

---

## `GET /v1/catalog/full-stack-factors`

| | |
|---|---|
| **What it does** | Lists **12-factor** full-stack factor IDs and metadata (needed before `asset.full_stack` + 12×12 shock pack). |
| **What you send** | Nothing. Optional `X-API-Key`. |
| **What you get (200)** | `{ "factor_order": [ "revenue", "capex", ... ], "risk_factors": [ { "factor_id", "display_name", "description", ... }, ... ] }`. |
| **Errors** | **401** when API key required. |

---

## `POST /v1/calibration/preview`

| | |
|---|---|
| **What it does** | **Dry-run calibration**: resolves `dynamic_margins` (file / HTTP / Yahoo) into numeric **`margins`** on the shock pack. **No** Monte Carlo, no DSCR distribution. |
| **What you send** | JSON body = full **`ShockPackSpec`** (same shape as `shockpack` on simulate), often including `dynamic_margins`. Optional `X-API-Key`. |
| **What you get (200)** | `{ "resolved_shockpack": <ShockPackSpec with margins filled, dynamic_margins cleared>, "calibration_trace": { "steps", "resolved_margins" } | null, "response_help" }`. |
| **Errors** | **422** — validation errors on spec. **404/502** — bad file path or HTTP URL. Yahoo failures if symbol has no data. **401** when API key required. |

---

## `POST /v1/simulate/v0/base-case`

| | |
|---|---|
| **What it does** | **Deterministic** single path: zero random shocks, one scenario. Fast tie-out vs a spreadsheet baseline. |
| **What you send** | JSON body = **`AssetAssumptions`** only (the body is **not** wrapped in `{ "asset": ... }`). Optional headers: `X-API-Key`, `X-Azraq-User-Id`. |
| **What you get (200)** | **`BaseCaseResult`**: `metadata` (`execution_mode: "v0_base"`, `n_scenarios: 1`, …), `base` (point estimates: `dscr`, `irr_annual`, `annual_revenue`, `ebitda`, `debt_service`, `initial_equity`, multipliers, `effective_interest_rate`, optional NPV/EV fields), `response_help`. |
| **Errors** | **422** — invalid asset. **401** when API key required. |

---

## `POST /v1/simulate/asset`

| | |
|---|---|
| **What it does** | Main **Monte Carlo** for **one** asset: many correlated scenarios, distributions of DSCR, IRR, covenant breach probability, etc. Optional attribution and full-stack outputs. |
| **What you send** | JSON **`AdhocSimulationRequest`**: **`asset`** (required); **`shockpack`** and/or **`shockpack_catalog_entry_id`** (at least one required). Optional: `include_attribution`, `include_advanced_attribution`, `attribution_tail_fraction`, `performance_profile` (`interactive` \| `standard` \| `deep`). Optional `X-API-Key`, `X-Azraq-User-Id`. |
| **What you get (200)** | **`SimulationResult`**: `metadata` (run id, seed, `n_scenarios`, `sampling_method`, `compute_time_ms`, optional `margin_calibration_trace`, catalogue id, …), `metrics` (**`FinancialRiskMetrics`**: DSCR/IRR distributions, `covenant_breach_probability`, EBITDA/levered CF/NAV summaries, tail proxies, …), optional `attribution`, optional `full_stack`, optional `extensions`, `response_help`. |
| **Errors** | **422** — missing shockpack/catalog id, invalid matrices, full-stack mismatch, etc. **401** when API key required. |

---

## `POST /v1/simulate/scheduled/asset`

| | |
|---|---|
| **What it does** | Same mathematics as **`POST /v1/simulate/asset`**, for **recurring / monitoring** runs. Can **persist** a JSON snapshot of the full result to disk. |
| **What you send** | JSON **`ScheduledAssetRequest`**: same fields as **`AdhocSimulationRequest`**, plus optional `label`, `persist` (default `true`), `model_version` (default `"azraq-mc-v1"`). Optional `X-API-Key`, `X-Azraq-User-Id`. |
| **What you get (200)** | **`ScheduledAssetResponse`**: `{ "result": <SimulationResult>, "snapshot_path": "<absolute path>" | null, "response_help" }`. Snapshot directory: **`AZRAQ_SNAPSHOT_DIR`** or default `data/snapshots`. |
| **Errors** | Same class as `/v1/simulate/asset` for validation. **401** when API key required. |

---

## `POST /v1/simulate/portfolio`

| | |
|---|---|
| **What it does** | **Joint** Monte Carlo: **one shock draw per scenario index** shared across **all** assets (minimum **2** assets). Portfolio-level breach and concentration metrics. |
| **What you send** | JSON **`PortfolioSimulationRequest`**: **`shockpack`** and/or **`shockpack_catalog_entry_id`**; **`portfolio_id`**, **`portfolio_assumption_set_id`**, **`assets`** (array of at least two **`AssetAssumptions`**). Optional `performance_profile`. Optional `X-API-Key`, `X-Azraq-User-Id`. |
| **What you get (200)** | **`PortfolioSimulationResult`**: `metadata` (portfolio run metadata), **`per_asset`** (each asset’s `FinancialRiskMetrics`), **`portfolio`** (e.g. `probability_any_covenant_breach`, `min_dscr_across_assets`, summed CF tails, …), `response_help`. |
| **Errors** | **422** — fewer than two assets, shock/spec mismatch, etc. **401** when API key required. |

---

## `POST /v1/shockpack/catalog/register`

| | |
|---|---|
| **What it does** | Saves a **`ShockPackSpec`** in the SQLite catalogue (and optional file artefact when configured) for reuse via **`shockpack_catalog_entry_id`** on simulate. |
| **What you send** | JSON body = **`ShockPackSpec`**. Query params: **`semver`** (default `1.0.0`), optional **`tenant_id`**, **`promotion_tier`** (`dev` \| `staging` \| `prod`, default `dev`), **`rbac_owner_role`** (default `editor`). Optional `X-API-Key`. |
| **What you get (200)** | `{ "entry_id": "<uuid>", "response_help" }` — store **`entry_id`** as **`shockpack_catalog_entry_id`**. |
| **Errors** | **422** — invalid spec. **401** when API key required. |

---

## `POST /v1/shockpack/catalog/{entry_id}/promote`

| | |
|---|---|
| **What it does** | Changes **`promotion_tier`** of a catalogue entry (governance: dev → staging → prod). |
| **What you send** | Path **`entry_id`**. Query **`to_tier`**: `dev` \| `staging` \| `prod`. Headers: **`X-API-Key`**, **`X-Azraq-Catalog-Role`** (unless `AZRAQ_CATALOG_PROMOTER_ROLES` is empty). |
| **What you get (200)** | `{ "ok": true, "response_help" }`. |
| **Errors** | **403** — role not allowed or tenant mismatch on other catalogue routes. **404** — unknown entry. **401** when API key required. |

---

## `GET /v1/shockpack/catalog/{entry_id}`

| | |
|---|---|
| **What it does** | Loads one catalogue row including the full stored **`spec`** (`ShockPackSpec` JSON). |
| **What you send** | Path **`entry_id`**. Optional **`X-Azraq-Tenant-Id`** — must match stored tenant when the entry is tenant-scoped. Optional `X-API-Key`. |
| **What you get (200)** | Catalogue row dict: ids, semver, tenant, **`spec`**, hashes, optional **`object_uri`**, etc., plus **`response_help`**. |
| **Errors** | **403** — tenant mismatch. **404** — not found. **401** when API key required. |

---

## `GET /v1/shockpack/catalog`

| | |
|---|---|
| **What it does** | Lists recent catalogue entries (**metadata**; use **GET by id** for full `spec`). |
| **What you send** | Query **`limit`** (default `100`), optional **`tenant_id`**, optional **`promotion_tier`**. Header **`X-Azraq-Tenant-Id`** may filter when `tenant_id` query omitted. Optional `X-API-Key`. |
| **What you get (200)** | `{ "entries": [ ... ], "response_help" }`. |
| **Errors** | **401** when API key required. |

---

## `POST /v1/shockpack/export/npz`

| | |
|---|---|
| **What it does** | Materialises correlated shock draws **`Z`** to a **NumPy `.npz`** file on disk for offline use. **No** DSCR/IRR in the file. |
| **What you send** | JSON **`ShockExportRequest`**: **`shockpack`** (required), optional **`directory`** (else env **`AZRAQ_SHOCK_EXPORT_DIR`** or default `data/shockpacks`). Optional `X-API-Key`. |
| **What you get (200)** | `{ "path": "<absolute .npz path>", "response_help" }`. |
| **Errors** | **422** — invalid spec. **401** when API key required. |

---

## `POST /v1/snapshots/save`

| | |
|---|---|
| **What it does** | Writes an **already computed** result (`SimulationResult`, `PortfolioSimulationResult`, or `BaseCaseResult`) to a **JSON** file under the snapshot root. |
| **What you send** | JSON **`SnapshotSaveRequest`**: optional **`label`**, **`result`** (full prior simulate response body). Optional `X-API-Key`. |
| **What you get (200)** | `{ "path": "<absolute path>", "response_help" }`. |
| **Errors** | **422** — bad payload. **401** when API key required. |

---

## `GET /v1/snapshots/list`

| | |
|---|---|
| **What it does** | Lists snapshot **file paths** under **`AZRAQ_SNAPSHOT_DIR`** (or default `data/snapshots`). |
| **What you send** | Nothing. Optional `X-API-Key`. |
| **What you get (200)** | `{ "paths": [ "<absolute path>", ... ], "response_help" }`. |
| **Errors** | **401** when API key required. |

---

## `GET /v1/audit/runs`

| | |
|---|---|
| **What it does** | Returns recent **audited** simulation rows from SQLite (HTTP/WebSocket runs), if audit DB exists and is enabled. |
| **What you send** | Query **`limit`** (default **50**). Optional `X-API-Key`. |
| **What you get (200)** | `{ "runs": [ { "run_id", "run_kind", "asset_id", "shockpack_id", "seed", "n_scenarios", "created_at_utc", "client_hint", ... }, ... ], "response_help" }`. Empty `runs` if DB missing/disabled. |
| **Errors** | **401** when API key required. |

---

## `POST /v1/snapshots/diff/asset-metrics`

| | |
|---|---|
| **What it does** | Compares two **saved** single-asset Monte Carlo JSON files: metric deltas plus **provenance** deltas (what inputs changed). |
| **What you send** | JSON `{ "before_path": "<server path>", "after_path": "<server path>" }` (paths from `snapshots/list` or scheduled `snapshot_path`). Optional `X-API-Key`. |
| **What you get (200)** | `{ "metrics_delta": { ... }, "provenance_delta": { ... }, "response_help" }` (shape from `diff_simulation_results`). |
| **Errors** | **400** — either file is not an asset **`SimulationResult`**. **401** when API key required. |

---

## `WebSocket /ws/v1/simulate/portfolio`

| | |
|---|---|
| **What it does** | Same **portfolio joint simulation** as **`POST /v1/simulate/portfolio`**, with optional **progress** messages for long runs. |
| **What you send** | Connect; if **`AZRAQ_API_KEY`** is set, handshake header **`x-api-key`**. After accept, send **one** JSON message = **`PortfolioSimulationRequest`** (same as HTTP body). |
| **What you get** | Server messages: zero or more `{ "type": "progress", "done": i, "of": n }`, then `{ "type": "result", "body": <PortfolioSimulationResult JSON> }`. On failure: `{ "type": "error", "detail": "..." }`, then connection closes. Unauthorized: `{ "type": "error", "detail": "Unauthorized" }`, close **4401**. |
| **Errors** | Validation/runtime errors returned as **`type: error`** message; see `detail`. |

---

## Shared request shapes (quick pointer)

| Name | Used on |
|------|--------|
| **`AssetAssumptions`** | Base case body; `asset` in simulate requests; `assets[]` in portfolio. |
| **`ShockPackSpec`** | `shockpack` field; calibration preview body; catalogue register body; export body. |
| **`AdhocSimulationRequest`** | `asset` + `shockpack` and/or `shockpack_catalog_entry_id`; optional attribution and `performance_profile`. |

Field-level detail, `dynamic_margins`, correlation sizes, and full-stack rules: **[API.md](API.md)** and **`/docs`** OpenAPI schemas.
