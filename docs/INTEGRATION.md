# Integration quick guide

**Full single-document guide:** **[Azraq_Monte_Carlo_API_Reference.md](Azraq_Monte_Carlo_API_Reference.md)** (versions, flow, all routes).

Short reference for plugging **your data** into the Monte Carlo API. **Every route, parameters, and response shapes:** **[ENDPOINTS.md](ENDPOINTS.md)**. Narrative + examples: **[API.md](API.md)**. Live **OpenAPI** at `/docs` and `/openapi.json` on a running server.

---

## 1. Base URL

Use your deployed host, e.g. `https://api.example.com` or local `http://127.0.0.1:8000`.

---

## 2. Primary call (single project)

| | |
|--|--|
| **Method / path** | `POST /v1/simulate/asset` |
| **Body** | JSON **`AdhocSimulationRequest`**: at minimum **`asset`** + **`shockpack`** |
| **Response** | **`SimulationResult`**: **`metadata`**, **`metrics`**, optional **`attribution`**, etc. |

**Health check (no API key on typical setups):** `GET /health`

---

## 3. Authentication & headers

| Env / config | Client header |
|--------------|----------------|
| If **`AZRAQ_API_KEY`** is set on the server | Send **`X-API-Key: <same value>`** on requests that require it (**`GET /health`** is usually public). |

Optional audit labels (not login):

- **`X-Azraq-User-Id`**
- **`X-Azraq-Tenant-Id`** (used for some catalogue routes)

---

## 4. “Reset” and state

The service is **stateless**: each **`POST /v1/simulate/asset`** is independent. There is **no server-side session** to clear. To “reset,” **discard the previous response** and **POST new JSON**.

To **persist** full JSON snapshots on the server for later diffing, see **`POST /v1/simulate/scheduled/asset`** in **[API.md](API.md)**.

---

## 5. Minimal request shape

```json
{
  "shockpack": {
    "shockpack_id": "your-pack-id",
    "seed": 42,
    "n_scenarios": 2500,
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
    "asset_id": "your-asset-id",
    "assumption_set_id": "your-label",
    "horizon_years": 15,
    "base_revenue_annual": 42000000,
    "base_opex_annual": 18000000,
    "utility_opex_annual": 0,
    "initial_capex": 280000000,
    "equity_fraction": 0.35,
    "tax_rate": 0,
    "financing": {
      "debt_principal": 182000000,
      "interest_rate_annual": 0.065,
      "loan_term_years": 18,
      "covenant_dscr": 1.2
    }
  },
  "include_attribution": false,
  "performance_profile": "interactive"
}
```

**`performance_profile`:** `interactive` caps scenario count for responsiveness; `standard` / `deep` allow larger **`n_scenarios`** (see **[API.md](API.md)**).

---

## 6. What to read from the response

| Your product need | Typical field under **`metrics`** |
|-------------------|-------------------------------------|
| DSCR distribution | **`dscr`** (p05, p50, p95, …) |
| IRR distribution | **`irr_annual`** |
| P(covenant breach) | **`covenant_breach_probability`** |
| Tail / VaR-style IRR | **`var_irr_95`**, **`cvar_irr_95`** (when populated) |
| Build cost distribution | **`total_capex`** (when present) |

Exact shapes are in **OpenAPI** (`/openapi.json`).

---

## 7. Mapping checklist (your data → API)

| Your field / concept | API location |
|---------------------|--------------|
| Project / case id | **`asset.asset_id`**, **`asset.assumption_set_id`** |
| Model horizon | **`asset.horizon_years`** |
| Revenue, opex, capex | **`asset.base_revenue_annual`**, **`base_opex_annual`**, **`initial_capex`** |
| Equity share | **`asset.equity_fraction`** (decimal, e.g. `0.35`) |
| Debt, coupon, term, DSCR floor | **`asset.financing`**: **`debt_principal`**, **`interest_rate_annual`** (decimal), **`loan_term_years`**, **`covenant_dscr`** |
| Shock count / reproducibility | **`shockpack.n_scenarios`**, **`shockpack.seed`** |
| Volatility / margins | **`shockpack.margins`** (and optional **`dynamic_margins`** for Yahoo/file/HTTP calibration — **[API.md](API.md)**) |

---

## 8. Optional next steps

- **Catalogue-managed shock packs:** register a base spec, then call with **`shockpack_catalog_entry_id`** + optional inline **`shockpack`** patch — see **[API.md](API.md)**.
- **Portfolio:** **`POST /v1/simulate/portfolio`** for multiple correlated assets.
- **Codegen:** import **`/openapi.json`** into your stack (OpenAPI generators, Postman, etc.).

---

## 9. Support files in this repo

| Doc | Use |
|-----|-----|
| **[ENDPOINTS.md](ENDPOINTS.md)** | All routes — parameters, bodies, responses, how to send/receive |
| **[API.md](API.md)** | Narrative reference, examples, **`response_help`**, deep interpretation |
| **[PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)** | Product-level picture of the engine |
| **[MONTE_CARLO_FLOW_AND_VALIDATION.md](MONTE_CARLO_FLOW_AND_VALIDATION.md)** | Flowcharts, shock semantics, step-by-step checks that your data moves outputs |
| **[SCENARIO_LAB_NON_TECH_GUIDE.md](SCENARIO_LAB_NON_TECH_GUIDE.md)** | Plain-language flow + steps for the investor **Scenario Lab** UI (`/app/`) |
