# Monte Carlo: information flow, shocks, and how to validate with your data

**Full single-document guide:** **[Azraq_Monte_Carlo_API_Reference.md](Azraq_Monte_Carlo_API_Reference.md)**.

This document is for teams who can call the API but need a **clear picture of what travels where**, what **“shocks”** mean in this product, and **how to prove** that your own numbers actually move the results. It complements **[INTEGRATION.md](INTEGRATION.md)** (minimal request) and **[API.md](API.md)** (full route reference).

---

## 1. Two separate layers (this is the mental model)

| Layer | JSON object | Role |
|-------|-------------|------|
| **Project economics** | `asset` (`AssetAssumptions`) | *Your* deal: revenue, opex, capex, horizon, financing, covenant floor, optional transforms / full-stack flags. **No randomness here**—these are the baseline inputs the engine stresses. |
| **Uncertainty model** | `shockpack` (`ShockPackSpec`) | *How the world wobbles*: how many scenarios, seed, sampling method, **which risk factors** (`factor_order`), **how volatile** each is (`margins`), **how they move together** (`correlation`, `copula`), optional **paths over time** (`time_grid`), optional **calibration from files/HTTP/Yahoo** (`dynamic_margins`). |

**Monte Carlo** = draw many correlated random **shock vectors** → for each draw, recompute coverage / cashflow-style metrics → summarise as distributions (percentiles, breach probability, etc.).

**Shocks are not “events” you type in one-by-one** (like “−20% revenue”). They are **parameters of random draws**: e.g. lognormal volatility on revenue (`revenue_log_sigma`) plus correlation with capex, opex, and rate. A **stress** in the colloquial sense is achieved by **changing those parameters** (wider sigmas, different correlation, or deterministic bumps via `factor_transforms` on the asset—see §4).

---

## 2. End-to-end flow (what to call, in order)

**Start here — five steps (no diagram required)**

1. Build **`asset`** (`AssetAssumptions`) from your spreadsheet or systems — the project as numbers you believe today.
2. Build **`shockpack`** (`ShockPackSpec`) — how many scenarios, seed, volatilities, correlation, optional **`dynamic_margins`** (Yahoo / file / HTTP).
3. **Optional:** `POST /v1/calibration/preview` with that shockpack — confirms external data filled **`margins`** without running MC (see **`calibration_trace`**).
4. **`POST /v1/simulate/v0/base-case`** with **`asset` only** — one deterministic row; must match your spreadsheet logic before you trust random runs.
5. **`POST /v1/simulate/asset`** with **`asset` + `shockpack`** — full Monte Carlo; read **`SimulationResult.metrics`**.

**Same idea as a simple picture (read top → bottom)**

```
YOUR SYSTEMS / EXCEL
        |
        +-------- asset JSON --------------+
        |                                  |
        +-------- shockpack JSON ----------+-----> (optional) calibration preview
        |                                  |              |
        v                                  v              v
   base-case POST                    simulate/asset POST   trace / resolved margins
   (sanity, no MC)                   (Monte Carlo)
        |                                  |
        v                                  v
   one deterministic outcome          distributions + breach %
```

**Optional later (only if you need them)**

- **Several projects together:** `POST /v1/simulate/portfolio` (2+ assets, one shared shock world).
- **Save and compare runs:** `POST /v1/snapshots/save` and `GET /v1/snapshots/diff/asset-metrics`.
- **Reuse a stored shockpack:** `POST /v1/shockpack/catalog/register` then call simulate with **`shockpack_catalog_entry_id`**.
- **Browse stress-source ideas:** `GET /v1/calibration/stress-data-catalog`; **inspect** a series: `GET /v1/market/yfinance/{symbol}/history` (does not run MC by itself).

**Endpoint one-liners**

- **`POST /v1/simulate/v0/base-case`**: same `asset` shape as MC, **no** random draws — align with a spreadsheet first.
- **`POST /v1/calibration/preview`**: turns **`dynamic_margins`** into concrete **`margins`**; no simulation. Use **`calibration_trace`** / run **`metadata.margin_calibration_trace`** to prove real data landed.
- **`POST /v1/simulate/asset`**: main MC — **`asset` + `shockpack`** → **`SimulationResult`**.

---

## 2a. `POST /v1/simulate/asset` — full server flow (flowchart)

**Who this is for:** anyone who wants to see what happens **after** the HTTP POST, in one picture.

**Flowchart (read top → bottom)**

```
  CLIENT
    |
    |  HTTP POST  /v1/simulate/asset
    |  JSON body: AdhocSimulationRequest
    |    - asset (required)
    |    - shockpack  OR  shockpack_catalog_entry_id  (or both: catalogue base + patch)
    |    - optional: performance_profile, include_attribution, ...
    v
  +---------------------------+
  | API key check (if         |   Header X-API-Key when server requires it
  |  AZRAQ_API_KEY set)       |
  +-------------+-------------+
                v
  +---------------------------+
  | Resolve final Shock pack   |
  +-------------+-------------+
                |
        If catalogue id in body:
                -> load stored ShockPackSpec
                -> if inline shockpack too: patch only fields you sent
        Else:
                -> inline shockpack required (full spec in request)
                |
                v
  +---------------------------+
  | run_adhoc_asset_simulation |
  +-------------+-------------+
                v
  +---------------------------+
  | Apply performance_profile |   May cap n_scenarios (e.g. interactive UI)
  +-------------+-------------+
                v
  +---------------------------+
  | materialize_shockpack_     |   file / HTTP / Yahoo -> margins;
  | margins                    |   trace -> metadata.margin_calibration_trace
  +-------------+-------------+
                v
  +---------------------------+
  | get_or_build_shock_array   |   Build random draws Z (or reuse cache)
  +-------------+-------------+
                v
  +---------------------------+
  | financial_impact           |   Each scenario: shocks + asset -> outcomes
  | (optional pipeline cache   |   Skip recompute if same fingerprint hit
  |  may return cached paths)  |
  +-------------+-------------+
                v
  +---------------------------+
  | build_financial_metrics    |   Distributions, covenant_breach_probability, …
  | (+ full_stack metrics      |   If asset.full_stack enabled and layer present
  |   when applicable)         |
  +-------------+-------------+
                v
  +---------------------------+
  | Optional attribution       |   If include_attribution (and advanced flags)
  +-------------+-------------+
                v
  +---------------------------+
  | Assemble SimulationResult  |   metadata, metrics, attribution?, extensions?
  | audit_simulation(...)      |
  +-------------+-------------+
                v
        HTTP 200 + JSON SimulationResult
```

**Explain the flowchart (plain language)**

1. **You send one request** with the **project** (`asset`) and how to draw risk (**`shockpack`** and/or a **catalogue id** that points at a saved shock pack).

2. **Resolve** picks the **final shock recipe**: catalogue row first, then any fields you put inline **fill in or override** missing pieces. You cannot omit both catalogue and inline pack.

3. **Performance profile** can **reduce** scenario count for speed (`interactive` / `standard`); `deep` does not cap.

4. **Materialize margins** runs **before** random draws: if the shock pack asked for Yahoo/file/HTTP calibration, those numbers are merged into **`margins`** now. Check **`metadata.margin_calibration_trace`** to prove what happened.

5. **Shock array** builds (or loads from cache) the correlated random **`Z`** for all scenarios.

6. **Financial impact** walks every scenario through the model (or reuses cached outcomes when the pipeline cache hits).

7. **Metrics** turns raw paths into **percentiles**, **breach probability**, optional tail stats, optional **full_stack** block.

8. **Attribution** (only if requested) adds **“what drove the bad tail”** style diagnostics — indicative, not a bank sign-off.

9. **Response** is **`SimulationResult`** JSON; the server also **writes an audit row** for the run.

**One line:** **`POST /v1/simulate/asset` = merge shock recipe → calibrate margins → draw shocks → value the asset many times → summarise → return JSON.**

---

## 3. What happens inside one Monte Carlo run (simplified)

**Relation to §2a:** The numbered steps below are the **inside** of the `run_adhoc_asset_simulation` box in **§2a** (from “materialize margins” through “metrics”). §2a adds the **HTTP**, **resolve shock pack**, and **response/audit** wrapper.

This section is **one request on the server** — not the order you build JSON in your team.

**One-line picture**

```
  shockpack  -->  (optional) fill margins from Yahoo / file / HTTP
                    |
                    v
              draw random Z  (many scenarios)
                    |
  asset  -----------+------->  value each scenario (DSCR, IRR, …)
                    |
                    v
              pack into metrics (percentiles, breach %)
```

**Steps (read 1 → 4)**

1. **Lock in margins (optional calibration):** If `dynamic_margins` is set, the service **merges** file / HTTP / Yahoo into **`margins`**, then drops `dynamic_margins` from the resolved spec. Proof: **`margin_calibration_trace`** on the run when used.
2. **Draw random shocks:** Build **Z** (correlated normals / Student‑t scaling), size from `n_scenarios`, `factor_order`, `correlation`, `copula`, optional `time_grid`.
3. **Map shocks to cash drivers:** Apply optional **`asset.factor_transforms`**, then lognormal / rate rules from **`margins`** so each scenario has stressed revenue, capex, opex, rate paths.
4. **Summarise:** Each scenario yields DSCR, IRR, etc.; the API returns percentiles and **`covenant_breach_probability`** in **`metrics`**.

**Code names (only if you grep the repo):** `materialize_shockpack_margins` → `get_or_build_shock_array` → `financial_impact`.

So: **`margins` control how wide** the distributions are; **`correlation`** controls **joint bad years**; **`asset.*`** controls **the size of the machine** being shocked.

---

## 4. Shock-related fields and what they do to outputs

| Input (typical) | Effect on the run |
|-----------------|-------------------|
| `n_scenarios` | More scenarios → smoother percentiles; law of large numbers (diminishing noise). |
| `seed` | Reproducibility: same seed + same spec → same Z (subject to performance/cache notes in API docs). |
| `sampling_method` | `monte_carlo` vs `latin_hypercube` / `sobol` — changes **how** space is filled, not the marginal distributions. |
| `factor_order` + `correlation` | Must be square and same length. Higher positive correlation between revenue and opex (for example) moves **joint** tail risk. |
| `margins.revenue_log_sigma` (etc.) | **Wider** log σ → **wider** revenue (and downstream DSCR / IRR) distribution; breach probability often **rises** if downside matters for covenant. |
| `margins.rate_shock_sigma` | Volatility of **additive** shocks to the **annual** interest rate (decimal σ); increases rate path dispersion. |
| `copula` / `t_degrees_freedom` | Gaussian vs heavier tails on the dependence structure. |
| `time_grid` | Multi-period Z: e.g. min DSCR over life vs single-period snapshot (see API narrative). |
| `asset.factor_transforms` | **Deterministic** scaling of shock indices or level multipliers (e.g. stress capex level) — useful when you want a **known** wedge on top of stochastic draws. |
| `macro_regime` | **Label** for audit / catalogue; does not by itself change maths unless you pair it with different specs per regime. |

**External “real data”** does **not** stream into every scenario. It is used to **set or update** the **`margins`** (and you verify that via **preview** or **`margin_calibration_trace`**).

---

## 5. Step-by-step: prove your data affects the outcome

Do these in order the first time you integrate.

### Step A — Health and contract

1. `GET /health` — environment up.
2. Open **`/openapi.json`** or **[ENDPOINTS.md](ENDPOINTS.md)** — this is the authoritative list of fields and types.

### Step B — Deterministic baseline (asset only)

1. `POST /v1/simulate/v0/base-case` with **only** your **`asset`** (same shape as in MC).
2. Check **`base`** metrics against your internal spreadsheet for the same inputs. If this fails, fix **`asset`** mapping before touching shocks.

### Step C — One-dimensional sensitivity (asset)

For each critical field (`base_revenue_annual`, `initial_capex`, `financing.interest_rate_annual`, `financing.covenant_dscr`, …):

1. Change **one** field by a **small, known** amount (e.g. +5% revenue).
2. Re-run base-case; confirm the output moves in the **direction you expect** (e.g. higher revenue → better coverage if nothing else breaks validation).

This proves **your economic payload** is wired.

### Step D — Shock width sensitivity (shockpack)

Fix **`asset`** and **`seed`**. Run `POST /v1/simulate/asset` twice:

1. **Low vol:** small `revenue_log_sigma`, `capex_log_sigma`, `opex_log_sigma`, `rate_shock_sigma`.
2. **High vol:** multiply those sigmas by e.g. **2×** (keep correlation identical).

**Expect:** breach probability and dispersion of DSCR / IRR **increase** with higher σ. If nothing moves, you are likely not hitting the simulate route you think you are, or metrics are cached from an identical fingerprint—compare **`metadata.run_id`** and request bodies.

### Step E — Calibration path (optional)

1. Put a minimal margin patch in JSON or Excel; reference it in **`dynamic_margins.file`**, or configure **`dynamic_margins.yahoo_finance`** with a liquid symbol.
2. `POST /v1/calibration/preview` with the same `shockpack` you intend to use.
3. Read **`resolved_shockpack.margins`** and **`calibration_trace`**. Confirm numbers match your file / Yahoo-derived expectation.
4. Run **`POST /v1/simulate/asset`** and confirm **`metadata.margin_calibration_trace`** is populated and consistent with preview.

### Step F — Portfolio (if applicable)

1. Two assets, shared **`shockpack`**, `POST /v1/simulate/portfolio`.
2. Toggle correlation between a macro factor shared across assets (via **`correlation`**) and confirm **portfolio** breach / joint tail metrics respond.

---

## 6. Short “video” outline (e.g. 8-minute screen recording)

If you record a walkthrough (Loom, Teams, etc.), this sequence matches **§2** above and builds confidence:

1. **0:00–0:45** — Show `/docs` + `openapi.json`; say “two blocks: `asset` + `shockpack`”.
2. **0:45–2:30** — Base-case POST: paste minimal `asset`, show response vs a spreadsheet row.
3. **2:30–4:30** — Same `asset`, two MC runs: low vs high `*_log_sigma`; show `covenant_breach_probability` and DSCR percentiles.
4. **4:30–6:30** — Calibration preview: `dynamic_margins` with a tiny JSON file or one Yahoo binding; show resolved margins + trace.
5. **6:30–8:00** — Full simulate with trace; point to **`response_help`** in JSON for non-technical readers.

---

## 7. Where to read more

| Topic | Document |
|-------|----------|
| Minimal POST body | **[INTEGRATION.md](INTEGRATION.md)** §5 |
| Every route and parameter | **[ENDPOINTS.md](ENDPOINTS.md)** |
| Narrative + `response_help` + market routes | **[API.md](API.md)** |
| Why external data exists and how it maps | **[PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)** |

---

## 8. One-line summary for stakeholders

**You supply a deterministic project model (`asset`) and a stochastic specification (`shockpack`); the API returns distributions of financial outcomes. External series are optional helpers to set volatility parameters—verify them with calibration preview and `margin_calibration_trace`, then validate behaviour with base-case checks and controlled σ sensitivity.**
