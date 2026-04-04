# Monte Carlo project — simple overview

This note explains **what this repo is for**, **what is implemented today**, and **why / where external data sources** are used. For API details and every endpoint, see **[API.md](API.md)**.

---

## What this project is about

**Azraq Monte Carlo** is a **risk engine** for infrastructure / data-centre style projects. It answers questions such as:

- If revenue, costs, interest rates, and (optionally) delivery or power stresses move in a realistic, **correlated** way, how bad can **debt coverage (DSCR)** get?
- What is the **chance of breaking a loan covenant**?
- For a **portfolio** of sites, what is the chance **any** site is in trouble when the same bad macro year hits everyone?

It does this by running **many random “what-if” worlds** (Monte Carlo), not a single spreadsheet row.

**Important:** The core simulator works on **numbers you choose** (distributions and correlations). It does **not** need the internet or live market feeds to run. External data is **optional** and is used to help **set** those numbers (calibration) or to **inspect** markets—not to drive each scenario tick-by-tick from the web.

---

## What we have implemented (high level)

| Area | What it does |
|------|----------------|
| **Single-asset simulation** | Many correlated shocks → distributions of DSCR, IRR, covenant breach probability, cash-flow style summaries, optional tail metrics. |
| **Portfolio simulation** | Same shock draw per scenario across **two or more** assets; book-level breach and “weakest link” style metrics. |
| **Base case (no randomness)** | One deterministic path to check the model against a spreadsheet baseline. |
| **Time paths** | Optional multi-period shocks (e.g. quarterly paths) with min DSCR over time / mean EBITDA over time. |
| **Full-stack mode** | Optional **12-factor** layer: delivery delays, power, grid, cyber, PUE/WUE style stats, optional **CPM** (critical path) and **resource** contention sketch. |
| **Macro / inflation (light)** | Optional tenor-style aggregation for rate shocks; optional inflation pass-through on factor draws. |
| **Waterfall / liquidity (stylised)** | Optional DSRA/LC-style charges, sculpting on multi-period paths, liquidity runway–style outputs. |
| **Attribution** | Optional explanation of **which drivers** show up more in bad outcomes (indicative, not a bank sign-off). |
| **Caching** | Reuse random numbers when only **margins** or labels change; optional full-step cache for repeated runs. |
| **Shock pack catalogue** | Save and reload shock setups (SQLite + optional file artefact); promotion tiers; basic tenant/role hooks on some routes. |
| **Calibration** | **Preview** without simulating: resolve `dynamic_margins` (file / HTTP / Yahoo) into concrete numbers. |
| **Market / stress catalogue** | **Appendix J–style** list of stress drivers + official URLs + how they map to the engine (`GET /v1/calibration/stress-data-catalog`); **ECB** EUR/USD spot helper. |
| **Snapshots & drift** | Save results; compare two runs (metric deltas + what inputs changed). |
| **API usability** | Many responses include **`response_help`** in **plain English** (what you sent, what you got, what to do next). |

Some items are **stylised** (simple finance and operations), not a full investment-bank cashflow engine—but the **architecture** supports richer models later.

---

## Data sources — why, and where they are used

### Why use external data at all?

- The simulator needs **sensible volatility** and **correlations** (how big shocks tend to be, and how they move together).
- Teams often want those numbers to be **grounded in history** (e.g. commodity or equity volatility) or **official statistics** (e.g. ECB FX), instead of only guessing.
- **External data does not run inside each Monte Carlo path as a live feed.** It is used **before** or **beside** the run to **fill in parameters** or to **review** a series.

So: **data sources → help set or justify inputs** → then **Monte Carlo runs on those inputs**.

### Where each kind of source plugs in

| Source type | Typical use | Where in this project |
|-------------|-------------|------------------------|
| **Yahoo Finance** (via `yfinance`) | Historical prices → **volatility** for calibration; quick charts | `GET /v1/market/yfinance/...`, and **`ShockPackSpec.dynamic_margins.yahoo_finance`** (resolved in `POST /v1/calibration/preview` or before simulate). |
| **ECB (European Central Bank)** | Official **EUR/USD** daily reference | `GET /v1/market/ecb/eur-usd` reads public XML. You can copy values or build your own JSON margin file from it. |
| **HTTP JSON** | **Your** controlled URL returns a **margin patch** (same shape as a small JSON file). Lets you proxy **IEA, NY Fed SOFR, BoE SONIA**, internal ETL, etc., without putting vendor parsers in this repo. | **`dynamic_margins.http`** on `ShockPackSpec`. |
| **JSON or Excel on disk** | Margin patch as **JSON** or **`.xlsx`/`.xlsm`** (wide headers or `field`+`value` columns) | **`dynamic_margins.file`** (optional `sheet` for Excel). |
| **Manual** | Analyst types or pastes margins after downloading from any portal | Paste into `ShockPackSpec.margins` or register a shock pack in the **catalogue**. |
| **Stress catalogue (Appendix J)** | **Reference table**: what each driver means, example URLs, primary/secondary tier, suggested Yahoo symbol when applicable | **`GET /v1/calibration/stress-data-catalog`** — documentation + integration hints, not automatic ingestion of every vendor. |

### Local `data/` folder (Excel and SQLite)

The repo’s **`data/`** directory is for **datasets you maintain locally**—for example:

- **`GECM_2025_Key input.xlsx`** — project / model inputs you can transcribe into API payloads or a JSON margin patch.
- **`Bank of England  Database.xlsx`** — reference series (e.g. rates or SONIA-related context) to support calibration; the engine does **not** open this file automatically.
- **`Search.xlsx`** — auxiliary lookup or list you use while building shocks.

**`azraq_audit.sqlite3`** (if present) is a **local SQLite database** (e.g. audit / catalogue); it is listed in `.gitignore` like other `*.sqlite3` files so it is usually **not** committed.

**How this ties to the API:** put volatility / margin numbers into a sheet that matches the **`dynamic_margins.file`** layouts (**wide** row with headers like `revenue_log_sigma`, or **two columns** `field` + `value`), then set `"path": "data/your_margins.xlsx"` (and `"sheet"` if not the first tab). You can still use JSON or paste into `ShockPackSpec.margins`. Large reference workbooks (e.g. full BoE database) are best kept as **source material**—copy the few cells you need into a small calibration sheet the loader can read.

### One sentence summary

**The Monte Carlo engine needs parameters; Yahoo, ECB, files, and HTTP JSON are ways to fill or check those parameters—listed in the stress catalogue—while the actual simulation stays self-contained once you press “run.”**

---

## Where to read more

| Document | Content |
|----------|---------|
| **[API.md](API.md)** | Every endpoint, auth, examples, `response_help` pattern, Appendix J notes. |
| **Interactive docs** | Run the server and open `/docs`. |

---

*Last aligned with the codebase as an overview only; details may evolve—check `API.md` and OpenAPI for the current contract.*
