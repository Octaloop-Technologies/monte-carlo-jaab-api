/**
 * Portfolio (v2) lab — POST /v1/simulate/portfolio
 */
(function () {
  const API_KEY = "5hm4R9Rlj0x2sCresLa038nAeOQyU8LgDT-HHfJTrns";
  const rateCap = 0.45;

  const ASSET_PRESETS = [
    {
      asset_id: "wind-north",
      rev: 35e6,
      opex: 14e6,
      capex: 220e6,
      eqPct: 35,
      coupon: 6.2,
      term: 18,
      cov: 1.2,
      hz: 15,
      util: 0,
    },
    {
      asset_id: "solar-south",
      rev: 28e6,
      opex: 11e6,
      capex: 180e6,
      eqPct: 35,
      coupon: 6.5,
      term: 15,
      cov: 1.25,
      hz: 15,
      util: 0,
    },
    {
      asset_id: "storage-coast",
      rev: 12e6,
      opex: 4e6,
      capex: 95e6,
      eqPct: 40,
      coupon: 6.8,
      term: 12,
      cov: 1.15,
      hz: 12,
      util: 0,
    },
    {
      asset_id: "hydro-upstream",
      rev: 22e6,
      opex: 8e6,
      capex: 150e6,
      eqPct: 30,
      coupon: 5.9,
      term: 20,
      cov: 1.3,
      hz: 20,
      util: 0,
    },
  ];

  function readNum(id, fallback) {
    const el = document.getElementById(id);
    if (!el) return fallback;
    const raw = String(el.value).trim();
    if (raw === "") return fallback;
    const v = Number(raw);
    return Number.isFinite(v) ? v : fallback;
  }

  function escapeAttr(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function fmtPct(x) {
    if (x == null || Number.isNaN(x)) return "—";
    return (100 * x).toFixed(2) + "%";
  }

  function fmtNum(x, d) {
    if (x == null || Number.isNaN(x)) return "—";
    return Number(x).toFixed(d);
  }

  function sigmaFloor(v) {
    return Math.max(1e-6, Number(v) || 1e-6);
  }

  const CORR_PAIR_IDS = ["corr_r_cx", "corr_r_op", "corr_r_rt", "corr_cx_op", "corr_cx_rt", "corr_op_rt"];

  /** Pair order matches upper triangle (0,1)..(2,3) for factors revenue,capex,opex,rate */
  const CORR_PRESETS = {
    engine_default: [0.35, 0.25, 0.15, 0.45, 0.1, 0.05],
    independent: [0, 0, 0, 0, 0, 0],
    high_joint: [0.55, 0.45, 0.35, 0.5, 0.3, 0.2],
  };

  function clampCorr(x) {
    if (!Number.isFinite(x)) return 0;
    return Math.max(-1, Math.min(1, x));
  }

  function applyCorrPreset(presetKey) {
    const pairs = CORR_PRESETS[presetKey];
    if (!pairs) return;
    const sel = document.getElementById("corrPreset");
    if (sel) {
      sel.value = presetKey;
    }
    for (let i = 0; i < CORR_PAIR_IDS.length; i++) {
      const el = document.getElementById(CORR_PAIR_IDS[i]);
      if (el) el.value = String(pairs[i]);
    }
  }

  function buildCorrelationMatrix() {
    const p0 = clampCorr(readNum("corr_r_cx", 0.35));
    const p1 = clampCorr(readNum("corr_r_op", 0.25));
    const p2 = clampCorr(readNum("corr_r_rt", 0.15));
    const p3 = clampCorr(readNum("corr_cx_op", 0.45));
    const p4 = clampCorr(readNum("corr_cx_rt", 0.1));
    const p5 = clampCorr(readNum("corr_op_rt", 0.05));
    return [
      [1, p0, p1, p2],
      [p0, 1, p3, p4],
      [p1, p3, 1, p5],
      [p2, p4, p5, 1],
    ];
  }

  function bindCorrelationControls() {
    const preset = document.getElementById("corrPreset");
    if (!preset) return;
    preset.addEventListener("change", () => {
      const v = preset.value;
      if (v !== "custom") {
        applyCorrPreset(v);
      }
    });
    for (const id of CORR_PAIR_IDS) {
      const el = document.getElementById(id);
      if (el) {
        el.addEventListener("input", () => {
          if (preset.value !== "custom") {
            preset.value = "custom";
          }
        });
      }
    }
  }

  function buildShockpack() {
    const n = Math.floor(readNum("nScenarios", 2000));
    const seed = Math.floor(readNum("seed", 42));
    const copulaEl = document.getElementById("copulaKind");
    const copula = copulaEl && copulaEl.value === "student_t" ? "student_t" : "gaussian";
    const tdf = Math.max(2.1, readNum("copulaDf", 8));
    const sp = {
      shockpack_id: "frontend-portfolio-v2",
      seed,
      n_scenarios: Math.min(500_000, Math.max(100, n)),
      sampling_method: "monte_carlo",
      factor_order: ["revenue", "capex", "opex", "rate"],
      correlation: buildCorrelationMatrix(),
      copula,
      margins: {
        revenue_log_mean: 0,
        revenue_log_sigma: sigmaFloor(readNum("sigmaRev", 0.08)),
        capex_log_mean: 0,
        capex_log_sigma: sigmaFloor(readNum("sigmaCapex", 0.06)),
        opex_log_mean: 0,
        opex_log_sigma: sigmaFloor(readNum("sigmaOpex", 0.05)),
        rate_shock_sigma: Math.max(0, readNum("sigmaRate", 0.005)),
      },
    };
    if (copula === "student_t") {
      sp.t_degrees_freedom = tdf;
    }

    const yahooEl = document.getElementById("yahooCopper");
    if (yahooEl && yahooEl.checked) {
      const symEl = document.getElementById("yahooSymbol");
      const perEl = document.getElementById("yahooPeriod");
      const symbol = (symEl && String(symEl.value).trim()) || "HG=F";
      const period = (perEl && String(perEl.value).trim()) || "1y";
      sp.dynamic_margins = {
        yahoo_finance: [
          {
            symbol,
            period,
            target: "capex_log_sigma",
            scale: 1.0,
            annualization_factor: 252,
            min_observations: 20,
          },
        ],
      };
    }

    return sp;
  }

  function buildAssetFromSlot(slot) {
    const rev = readNum(`a${slot}_rev`, 30e6);
    const opex = readNum(`a${slot}_opex`, 12e6);
    const util = Math.min(readNum(`a${slot}_util`, 0), opex);
    const capex = readNum(`a${slot}_capex`, 200e6);
    const eqPct = readNum(`a${slot}_eq`, 35) / 100;
    let debt = readNum(`a${slot}_debt`, NaN);
    if (!Number.isFinite(debt) || debt < 0) {
      debt = capex * (1 - Math.min(0.99, Math.max(0.01, eqPct)));
    }
    const coupon = readNum(`a${slot}_coupon`, 6.5) / 100;
    const term = Math.floor(readNum(`a${slot}_term`, 15));
    const cov = readNum(`a${slot}_cov`, 1.2);
    const hz = Math.floor(readNum(`a${slot}_hz`, 15));
    const aidEl = document.getElementById(`a${slot}_id`);
    const aid = (aidEl && aidEl.value.trim()) || `asset-${slot}`;

    return {
      asset_id: aid,
      assumption_set_id: "frontend-portfolio",
      horizon_years: hz,
      base_revenue_annual: rev,
      base_opex_annual: opex,
      utility_opex_annual: util,
      initial_capex: capex,
      equity_fraction: Math.min(0.99, Math.max(0.01, eqPct)),
      tax_rate: 0,
      financing: {
        debt_principal: debt,
        interest_rate_annual: Math.min(rateCap, Math.max(0, coupon)),
        loan_term_years: Math.max(1, term),
        covenant_dscr: cov > 0 ? cov : 1.2,
      },
    };
  }

  function collectAssets(n) {
    const assets = [];
    for (let i = 1; i <= n; i++) {
      assets.push(buildAssetFromSlot(i));
    }
    const ids = assets.map((a) => a.asset_id);
    const dup = ids.filter((x, j) => ids.indexOf(x) !== j);
    if (dup.length) {
      throw new Error("Each asset needs a unique case name. Duplicate: " + [...new Set(dup)].join(", "));
    }
    return assets;
  }

  function renderAssetBlocks() {
    const sel = document.getElementById("numAssets");
    const n = sel ? parseInt(sel.value, 10) || 2 : 2;
    const root = document.getElementById("assetBlocks");
    if (!root) return;

    let html = "";
    for (let i = 0; i < n; i++) {
      const slot = i + 1;
      const p = ASSET_PRESETS[i] || ASSET_PRESETS[ASSET_PRESETS.length - 1];
      html +=
        '<div class="portfolio-asset-block" data-slot="' +
        slot +
        '">' +
        "<h3>Asset " +
        slot +
        "</h3>" +
        '<div class="portfolio-asset-grid">' +
        '<div class="field field--compact"><label class="field-label" for="a' +
        slot +
        '_id">Case name</label>' +
        '<input type="text" id="a' +
        slot +
        '_id" class="input-text" value="' +
        escapeAttr(p.asset_id) +
        '" /></div>' +
        '<div class="field field--compact"><label class="field-label" for="a' +
        slot +
        '_rev">Base revenue</label>' +
        '<input type="number" id="a' +
        slot +
        '_rev" class="input-text" step="any" value="' +
        p.rev +
        '" /></div>' +
        '<div class="field field--compact"><label class="field-label" for="a' +
        slot +
        '_opex">Base opex</label>' +
        '<input type="number" id="a' +
        slot +
        '_opex" class="input-text" step="any" value="' +
        p.opex +
        '" /></div>' +
        '<div class="field field--compact"><label class="field-label" for="a' +
        slot +
        '_capex">Initial capex</label>' +
        '<input type="number" id="a' +
        slot +
        '_capex" class="input-text" step="any" value="' +
        p.capex +
        '" /></div>' +
        '<div class="field field--compact"><label class="field-label" for="a' +
        slot +
        '_eq">Equity % of capex</label>' +
        '<input type="number" id="a' +
        slot +
        '_eq" class="input-text" step="0.5" min="1" max="99" value="' +
        p.eqPct +
        '" /></div>' +
        '<div class="field field--compact"><label class="field-label" for="a' +
        slot +
        '_debt">Debt (optional)</label>' +
        '<input type="number" id="a' +
        slot +
        '_debt" class="input-text" step="any" placeholder="auto" /></div>' +
        '<div class="field field--compact"><label class="field-label" for="a' +
        slot +
        '_coupon">Coupon % / yr</label>' +
        '<input type="number" id="a' +
        slot +
        '_coupon" class="input-text" step="0.05" value="' +
        p.coupon +
        '" /></div>' +
        '<div class="field field--compact"><label class="field-label" for="a' +
        slot +
        '_term">Loan term (yrs)</label>' +
        '<input type="number" id="a' +
        slot +
        '_term" class="input-text" step="1" min="1" value="' +
        p.term +
        '" /></div>' +
        '<div class="field field--compact"><label class="field-label" for="a' +
        slot +
        '_cov">DSCR covenant</label>' +
        '<input type="number" id="a' +
        slot +
        '_cov" class="input-text" step="0.05" value="' +
        p.cov +
        '" /></div>' +
        '<div class="field field--compact"><label class="field-label" for="a' +
        slot +
        '_hz">Horizon (yrs)</label>' +
        '<input type="number" id="a' +
        slot +
        '_hz" class="input-text" step="1" min="1" value="' +
        p.hz +
        '" /></div>' +
        '<div class="field field--compact"><label class="field-label" for="a' +
        slot +
        '_util">Utility opex</label>' +
        '<input type="number" id="a' +
        slot +
        '_util" class="input-text" step="any" value="' +
        p.util +
        '" /></div>' +
        "</div></div>";
    }
    root.innerHTML = html;
  }

  function syncRequestPreview(body) {
    const ta = document.getElementById("reqJson");
    if (ta) ta.value = JSON.stringify(body, null, 2);
  }

  function renderPseudoHistogram(containerId, summary, formatX, titleTag) {
    const el = document.getElementById(containerId);
    if (!el) return;
    if (!summary || summary.p05 == null || summary.p10 == null || summary.p50 == null) {
      el.innerHTML = '<p class="chart-empty">—</p>';
      return;
    }
    const p90 = summary.p90 != null ? summary.p90 : summary.p50;
    const p95 = summary.p95 != null ? summary.p95 : p90;
    const edges = [summary.p05, summary.p10, summary.p50, p90, p95];
    const mass = [0.05, 0.4, 0.4, 0.1];
    const bins = [];
    for (let i = 0; i < 4; i++) {
      const a = edges[i];
      const b = edges[i + 1];
      const w = Math.abs(b - a) || 1e-9;
      bins.push({ lo: Math.min(a, b), hi: Math.max(a, b), h: mass[i] / w });
    }
    const hMax = Math.max(...bins.map((b) => b.h));
    const bars = bins
      .map((b) => {
        const pct = (b.h / hMax) * 100;
        const mid = (b.lo + b.hi) / 2;
        return (
          '<div class="pseudo-bin" title="' +
          formatX(b.lo) +
          " – " +
          formatX(b.hi) +
          '"><div class="pseudo-bin-fill" style="height:' +
          pct.toFixed(1) +
          '%"></div><span class="pseudo-bin-x">' +
          formatX(mid) +
          "</span></div>"
        );
      })
      .join("");
    el.innerHTML =
      (titleTag ? '<p class="pseudo-hist-title">' + titleTag + "</p>" : "") +
      '<div class="pseudo-hist">' +
      bars +
      '</div><p class="chart-caption chart-caption--tight">Sketch from reported quantiles (not raw buckets).</p>';
  }

  function renderPortfolioKpis(portfolio, meta) {
    const row = document.getElementById("pfKpiRow");
    if (!row || !portfolio) return;

    const minD = portfolio.min_dscr_across_assets || {};
    const tiles = [
      {
        k: "P(any covenant breach)",
        v: fmtPct(portfolio.probability_any_covenant_breach),
        sub: "At least one asset below its floor in a scenario",
      },
      {
        k: "Assets · scenarios",
        v: String(portfolio.n_assets) + " · " + String(portfolio.scenarios),
        sub: meta && meta.run_id ? "run " + meta.run_id.slice(0, 8) + "…" : "",
      },
      {
        k: "Min DSCR across pool (p50)",
        v: minD.p50 != null ? fmtNum(minD.p50, 3) : "—",
        sub: "Worst name in each path, then median",
      },
      {
        k: "Weighted breach exposure",
        v:
          portfolio.weighted_covenant_breach_exposure != null
            ? fmtPct(portfolio.weighted_covenant_breach_exposure)
            : "—",
        sub: "Revenue-weighted simultaneous stress (see API)",
      },
    ];

    row.innerHTML = tiles
      .map(
        (t) =>
          '<div class="kpi-tile"><h4 class="kpi-label">' +
          t.k +
          '</h4><p class="kpi-value">' +
          t.v +
          '</p><p class="kpi-sub">' +
          t.sub +
          "</p></div>"
      )
      .join("");
  }

  function renderAssetTable(perAsset) {
    const tbl = document.getElementById("pfAssetTable");
    if (!tbl || !Array.isArray(perAsset)) return;

    const head =
      "<thead><tr><th>Asset</th><th>P(breach)</th><th>DSCR p50</th><th>IRR p50</th><th>PD proxy</th></tr></thead><tbody>";
    const body = perAsset
      .map((row) => {
        const m = row.metrics || {};
        const dscr = m.dscr || {};
        const irr = m.irr_annual || {};
        const pd = m.probability_of_default_proxy_dscr_lt_1;
        return (
          "<tr><td>" +
          escapeAttr(row.asset_id || "") +
          "</td><td>" +
          fmtPct(m.covenant_breach_probability) +
          "</td><td>" +
          (dscr.p50 != null ? fmtNum(dscr.p50, 3) : "—") +
          "</td><td>" +
          (irr.p50 != null ? fmtNum(100 * irr.p50, 2) + "%" : "—") +
          "</td><td>" +
          (pd != null ? fmtPct(pd) : "—") +
          "</td></tr>"
        );
      })
      .join("");
    tbl.innerHTML = head + body + "</tbody>";
  }

  function renderPortfolioResults(data) {
    document.getElementById("pfResults").hidden = false;
    const raw = document.getElementById("pfRawOut");
    if (raw) raw.textContent = JSON.stringify(data, null, 2);

    const portfolio = data.portfolio;
    const meta = data.metadata;
    renderPortfolioKpis(portfolio, meta);
    renderAssetTable(data.per_asset);

    const minD = portfolio.min_dscr_across_assets;
    renderPseudoHistogram(
      "pfHistMinDscr",
      minD,
      (x) => fmtNum(x, 3),
      "Min DSCR (worst asset per scenario)"
    );

    const cf = portfolio.sum_levered_cf_year1;
    renderPseudoHistogram("pfHistCf", cf, (x) => fmtNum(x/1e6, 2) + "M", "Sum of Y1 levered CF (after tax)");

    if (portfolio.probability_at_least_k_breaches && Object.keys(portfolio.probability_at_least_k_breaches).length) {
      /* Table already shows per-asset; optional: could add footnote */
    }
  }

  async function runPortfolio() {
    const status = document.getElementById("pfStatus");
    status.textContent = "";
    status.classList.remove("err");

    const n = parseInt(document.getElementById("numAssets").value, 10) || 2;
    let assets;
    try {
      assets = collectAssets(n);
    } catch (e) {
      status.textContent = "Error: " + e.message;
      status.classList.add("err");
      return;
    }

    const shockpack = buildShockpack();
    const body = {
      portfolio_id: (document.getElementById("pfId").value || "portfolio").trim(),
      portfolio_assumption_set_id: (document.getElementById("pfAsId").value || "asof").trim(),
      assets,
      shockpack,
    };

    const nNum = shockpack.n_scenarios;
    body.performance_profile = nNum > 5000 ? "standard" : "interactive";

    syncRequestPreview(body);

    const headers = { "Content-Type": "application/json" };
    if (API_KEY) headers["X-API-Key"] = API_KEY;

    status.textContent = "Running joint simulation…";
    const res = await fetch("/v1/simulate/portfolio", {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
    const text = await res.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch {
      throw new Error(text.slice(0, 240) || res.statusText);
    }
    if (!res.ok) {
      const detail = data.detail || JSON.stringify(data);
      const msg = typeof detail === "string" ? detail : JSON.stringify(detail);
      if (res.status === 401) {
        throw new Error(
          "Unauthorized (401). Match API_KEY in portfolio.js to server AZRAQ_API_KEY; use same host as API."
        );
      }
      throw new Error(res.status + ": " + msg);
    }
    renderPortfolioResults(data);
    status.textContent = "Done.";
  }

  function bind() {
    const num = document.getElementById("numAssets");
    if (num) {
      num.addEventListener("change", renderAssetBlocks);
    }
    bindCorrelationControls();
    applyCorrPreset("engine_default");

    function syncYahooPanel() {
      const cb = document.getElementById("yahooCopper");
      const on = cb && cb.checked;
      const panel = document.getElementById("yahooPanel");
      if (panel) panel.classList.toggle("yahoo-panel--disabled", !on);
      const ys = document.getElementById("yahooSymbol");
      const yp = document.getElementById("yahooPeriod");
      if (ys) ys.disabled = !on;
      if (yp) yp.disabled = !on;
    }
    const yahooCb = document.getElementById("yahooCopper");
    if (yahooCb) {
      yahooCb.addEventListener("change", syncYahooPanel);
      syncYahooPanel();
    }

    const btn = document.getElementById("runPfBtn");
    if (btn) {
      btn.addEventListener("click", async () => {
        const status = document.getElementById("pfStatus");
        try {
          await runPortfolio();
        } catch (e) {
          status.textContent = "Error: " + e.message;
          status.classList.add("err");
        }
      });
    }
    renderAssetBlocks();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();
