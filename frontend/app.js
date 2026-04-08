/**
 * Investor-focused Monte Carlo dashboard — POST /v1/simulate/asset.
 * Structured inputs, scenario tabs, copper stress comparison, simplified KPIs + distribution sketches.
 */
(function () {
  const API_KEY = "5hm4R9Rlj0x2sCresLa038nAeOQyU8LgDT-HHfJTrns";

  const multMin = 0.05;
  const multMax = 5.0;
  const rateCap = 0.45;

  const SCENARIO_PRESETS = {
    base: { capexPct: 0, opexPct: 0, rateBps: 0 },
    rate_shock: { capexPct: 0, opexPct: 0, rateBps: 200 },
    cost_shock: { capexPct: 10, opexPct: 10, rateBps: 0 },
    combined: { capexPct: 10, opexPct: 10, rateBps: 200 },
  };

  let lastRunContext = { covenantDscr: 1.2 };
  let lastRawResult = null;

  function readNum(id, fallback = NaN) {
    const el = document.getElementById(id);
    if (!el) return fallback;
    const raw = String(el.value).trim();
    if (raw === "") return fallback;
    const v = Number(raw);
    return Number.isFinite(v) ? v : fallback;
  }

  function syncScenarioSliders(preset) {
    const c = document.getElementById("capexPct");
    const cr = document.getElementById("capexPctRange");
    const o = document.getElementById("opexPct");
    const or = document.getElementById("opexPctRange");
    const r = document.getElementById("rateBps");
    const rr = document.getElementById("rateBpsRange");
    if (c) c.value = String(preset.capexPct);
    if (cr) cr.value = String(preset.capexPct);
    if (o) o.value = String(preset.opexPct);
    if (or) or.value = String(preset.opexPct);
    if (r) r.value = String(preset.rateBps);
    if (rr) rr.value = String(preset.rateBps);
    updateScenarioHint();
  }

  function updateScenarioHint() {
    const el = document.getElementById("scenarioHint");
    if (!el) return;
    const cx = readNum("capexPct", 0);
    const ox = readNum("opexPct", 0);
    const bps = readNum("rateBps", 0);
    el.textContent =
      `Active shocks: Copper weight ${cx >= 0 ? "+" : ""}${cx}% on build cost, OPEX ${ox >= 0 ? "+" : ""}${ox}%, interest +${bps} bps on coupon.`;
  }

  function deepCopy(obj) {
    return JSON.parse(JSON.stringify(obj));
  }

  function buildAssetFromInvestorForm() {
    const rev = readNum("invRevenue", 42e6);
    const opex = readNum("invOpex", 18e6);
    const util = Math.min(readNum("invUtilityOpex", 0), opex);
    const capex = readNum("invCapex", 280e6);
    const eqPct = readNum("invEquityPct", 35) / 100;
    let debt = readNum("invDebt", NaN);
    if (!Number.isFinite(debt) || debt < 0) debt = capex * (1 - Math.min(0.99, Math.max(0.01, eqPct)));
    const coupon = readNum("invCoupon", 6.5) / 100;
    const term = Math.floor(readNum("invTerm", 18));
    const cov = readNum("invCovenant", 1.2);
    const horizon = Math.floor(readNum("invHorizon", 15));
    const aid = (document.getElementById("invAssetId") && document.getElementById("invAssetId").value.trim()) || "investor-case";

    return {
      asset_id: aid,
      assumption_set_id: "frontend-investor",
      horizon_years: horizon,
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

  function syncJsonPreview(asset) {
    const ta = document.getElementById("assetJson");
    if (ta) ta.value = JSON.stringify(asset, null, 2);
  }

  function parseShockInputs() {
    return {
      capexPct: readNum("capexPct", 0),
      opexPct: readNum("opexPct", 0),
      rateBps: readNum("rateBps", 0),
    };
  }

  function applyFactorTransform(asset, partial) {
    const a = deepCopy(asset);
    const base = {
      revenue_shock_scale: 1.0,
      capex_shock_scale: 1.0,
      opex_shock_scale: 1.0,
      rate_shock_scale: 1.0,
      revenue_level_multiplier: 1.0,
      capex_level_multiplier: 1.0,
      opex_level_multiplier: 1.0,
    };
    a.factor_transforms = { ...base, ...partial };
    return a;
  }

  function buildAssetWithShocks(baseAsset, shocks) {
    const { capexPct, opexPct, rateBps } = shocks;
    let a = deepCopy(baseAsset);
    const capexM = Math.min(multMax, Math.max(multMin, 1 + capexPct / 100));
    const opexM = Math.min(multMax, Math.max(multMin, 1 + opexPct / 100));
    if (capexPct !== 0 || opexPct !== 0) {
      a = applyFactorTransform(a, {
        capex_level_multiplier: capexM,
        opex_level_multiplier: opexM,
      });
    }
    if (rateBps !== 0) {
      a.financing = { ...a.financing };
      a.financing.interest_rate_annual = Math.min(
        rateCap,
        Math.max(0, a.financing.interest_rate_annual + rateBps / 10000)
      );
    }
    return a;
  }

  /** Independent log-σ style factors → single OPEX margin √(σ_e² + σ_c²). */
  function combinedOpexLogSigma() {
    const e = readNum("volElectricity", 0);
    const c = readNum("volCpi", 0);
    const se = Number.isFinite(e) ? Math.max(0, e) : 0;
    const sc = Number.isFinite(c) ? Math.max(0, c) : 0;
    const comb = Math.sqrt(se * se + sc * sc);
    return comb > 1e-12 ? comb : 0.05;
  }

  function buildShockpack(n, seed, useYahoo, yahooSymbol, yahooPeriod, yahooHistoryDays) {
    const sp = {
      shockpack_id: "frontend-investor-v0",
      seed: Number(seed),
      n_scenarios: Number(n),
      sampling_method: "monte_carlo",
      margins: {
        revenue_log_mean: 0,
        revenue_log_sigma: readNum("volFx", 0.08),
        capex_log_mean: 0,
        capex_log_sigma: readNum("volCopper", 0.06),
        opex_log_mean: 0,
        opex_log_sigma: combinedOpexLogSigma(),
        rate_shock_sigma: readNum("volInterest", 0.005),
      },
    };
    if (useYahoo) {
      const symbol = (yahooSymbol || "").trim() || "HG=F";
      const period = (yahooPeriod || "1y").trim() || "1y";
      const nd = yahooHistoryDays != null ? Number(yahooHistoryDays) : NaN;
      const binding = {
        symbol,
        period,
        target: "capex_log_sigma",
        scale: 1.0,
        annualization_factor: 252,
        min_observations: 20,
      };
      if (Number.isFinite(nd) && nd >= 1) {
        binding.history_days = Math.min(10000, Math.max(1, Math.floor(nd)));
      }
      sp.dynamic_margins = {
        yahoo_finance: [binding],
      };
    }
    return sp;
  }

  function formatPct(x) {
    if (x == null || Number.isNaN(x)) return "—";
    return (100 * x).toFixed(2) + "%";
  }

  function formatNum(x, d = 4) {
    if (x == null || Number.isNaN(x)) return "—";
    return Number(x).toFixed(d);
  }

  /** Piecewise-linear CDF from (p05,5%), (p50,50%), (p95,95%) → P(X < h). */
  function estimatePIrrBelowHurdle(irr, h) {
    if (!irr || irr.p05 == null || irr.p50 == null || irr.p95 == null || h == null || !Number.isFinite(h))
      return null;
    const pts = [
      [irr.p05, 0.05],
      [irr.p50, 0.5],
      [irr.p95, 0.95],
    ].sort((a, b) => a[0] - b[0]);
    const x = h;
    if (x <= pts[0][0]) return Math.max(0, Math.min(1, 0.05));
    if (x >= pts[2][0]) return Math.max(0, Math.min(1, 0.95));
    for (let i = 0; i < pts.length - 1; i++) {
      if (x <= pts[i + 1][0]) {
        const t = (x - pts[i][0]) / (pts[i + 1][0] - pts[i][0]);
        return Math.max(0, Math.min(1, pts[i][1] + t * (pts[i + 1][1] - pts[i][1])));
      }
    }
    return 0.5;
  }

  function bandDomain(values) {
    const pts = values.filter((x) => x != null && Number.isFinite(x));
    if (pts.length === 0) return { lo: 0, hi: 1 };
    let lo = Math.min(...pts);
    let hi = Math.max(...pts);
    const pad = (hi - lo) * 0.12 || 0.04;
    return { lo: lo - pad, hi: hi + pad };
  }

  function pctInDomain(v, lo, hi) {
    const s = hi - lo || 1e-9;
    return ((v - lo) / s) * 100;
  }

  function renderDscrCovenantBand(dscr, covenantDscr) {
    const el = document.getElementById("dscrBandChart");
    if (!el) return;
    if (dscr.p05 == null || dscr.p95 == null || dscr.p50 == null) {
      el.innerHTML = '<p class="chart-empty">Insufficient DSCR percentiles.</p>';
      return;
    }
    const cov = Number(covenantDscr);
    const { lo, hi } = bandDomain([dscr.p05, dscr.p95, cov]);
    const left = Math.max(0, Math.min(100, pctInDomain(dscr.p05, lo, hi)));
    const right = Math.max(0, Math.min(100, pctInDomain(dscr.p95, lo, hi)));
    const width = Math.max(1.5, right - left);
    const med = Math.max(0, Math.min(100, pctInDomain(dscr.p50, lo, hi)));
    const line = Math.max(0, Math.min(100, pctInDomain(cov, lo, hi)));
    el.innerHTML =
      '<div class="h-band-axis"><span>' +
      formatNum(lo, 3) +
      "</span><span>" +
      formatNum(hi, 3) +
      '</span></div><div class="h-band-track">' +
      '<div class="h-band-range" style="left:' +
      left +
      "%;width:" +
      width +
      '%"></div>' +
      '<div class="h-band-median" style="left:' +
      med +
      '%"></div>' +
      '<div class="h-band-ref h-band-ref--bad" style="left:' +
      line +
      '%"><span>Covenant ' +
      formatNum(cov, 2) +
      "</span></div></div>" +
      '<p class="h-band-legend">Green band ≈ typical range of <strong>debt service coverage</strong> (higher is safer). Red = bank minimum (' +
      formatNum(cov, 2) +
      ").</p>";
  }

  function renderIrrBandChart(irr, hurdleDec) {
    const el = document.getElementById("irrBandChart");
    if (!el) return;
    if (!irr || irr.p05 == null || irr.p95 == null || irr.p50 == null) {
      el.innerHTML = '<p class="chart-empty">No IRR distribution in this response.</p>';
      return;
    }
    const hurdle = hurdleDec != null && Number.isFinite(hurdleDec) ? hurdleDec : null;
    const pts = [irr.p05, irr.p95, 0, irr.p50];
    if (hurdle != null) pts.push(hurdle);
    const { lo, hi } = bandDomain(pts);
    const left = pctInDomain(irr.p05, lo, hi);
    const right = pctInDomain(irr.p95, lo, hi);
    const width = Math.max(1.5, right - left);
    const med = pctInDomain(irr.p50, lo, hi);
    const z = pctInDomain(0, lo, hi);
    let refs =
      '<div class="h-band-ref h-band-ref--zero" style="left:' + z + '%"><span>0%</span></div>';
    if (hurdle != null) {
      const hp = pctInDomain(hurdle, lo, hi);
      refs +=
        '<div class="h-band-ref h-band-ref--hurdle" style="left:' +
        hp +
        '%"><span>Target ' +
        (100 * hurdle).toFixed(1) +
        "%</span></div>";
    }
    el.innerHTML =
      '<div class="h-band-axis"><span>' +
      formatNum(lo, 3) +
      "</span><span>" +
      formatNum(hi, 3) +
      '</span></div><div class="h-band-track">' +
      '<div class="h-band-range h-band-range--irr" style="left:' +
      left +
      "%;width:" +
      width +
      '%"></div>' +
      '<div class="h-band-median" style="left:' +
      med +
      '%"></div>' +
      refs +
      "</div>" +
      '<p class="h-band-legend">IRR shown as decimals (0.08 = 8% per year). Grey = break-even; gold = your hurdle.</p>';
  }

  /**
   * Histogram-style bars from reported quantiles only (not raw simulation bins).
   * Bins between consecutive quantiles; height ∝ probability / bin width.
   */
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
      (titleTag ? "<p class=\"pseudo-hist-title\">" + titleTag + "</p>" : "") +
      '<div class="pseudo-hist">' +
      bars +
      '</div><p class="chart-caption chart-caption--tight">Shape is a <strong>sketch</strong> from p05–p95 (not individual Monte Carlo buckets).</p>';
  }

  function renderKpiRow(m, covenant, hurdleDec, nScenarios) {
    const row = document.getElementById("kpiRow");
    if (!row) return;
    const irr = m.irr_annual;
    const pBreach = m.covenant_breach_probability;
    const pIrr = estimatePIrrBelowHurdle(irr, hurdleDec);
    const capex = m.total_capex;
    const varIrr = m.var_irr_95;
    const covLab = formatNum(covenant, 2);

    const tiles = [
      {
        k: "Chance DSCR below " + covLab,
        v: formatPct(pBreach),
        sub:
          "From " +
          (nScenarios != null ? nScenarios : "N") +
          " simulated paths (API `covenant_breach_probability`).",
      },
      {
        k: "Approx. chance IRR below target",
        v: pIrr != null ? formatPct(pIrr) : "—",
        sub:
          hurdleDec != null
            ? "Estimated from IRR p05 / p50 / p95 (API does not return exact P(IRR<h))."
            : "Set hurdle % in Base inputs.",
      },
      {
        k: "P95 total CAPEX",
        v: capex && capex.p95 != null ? formatNum(capex.p95, 0) : "—",
        sub: "Stochastic nominal build cost per scenario (same units as your model).",
      },
      {
        k: "VaR IRR (95%)",
        v: varIrr != null ? formatNum(varIrr, 4) : "—",
        sub: "Shortfall vs median at the bad end (see API.md).",
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

  function renderCompareTable(rows) {
    const wrap = document.getElementById("compareWrap");
    const tbl = document.getElementById("tblCompare");
    if (!wrap || !tbl) return;
    if (!rows.length) {
      wrap.hidden = true;
      return;
    }
    wrap.hidden = false;
    const head =
      "<thead><tr><th>Scenario</th><th>CAPEX shock</th><th>P(DSCR&lt;cov)</th><th>≈P(IRR&lt;h)</th><th>P95 CAPEX</th><th>VaR IRR</th></tr></thead><tbody>";
    const body = rows
      .map(
        (r) =>
          "<tr><td>" +
          r.name +
          "</td><td>" +
          r.capexPct +
          '%</td><td>' +
          formatPct(r.pBreach) +
          "</td><td>" +
          (r.pIrr != null ? formatPct(r.pIrr) : "—") +
          "</td><td>" +
          (r.p95Capex != null ? formatNum(r.p95Capex, 0) : "—") +
          "</td><td>" +
          (r.varIrr != null ? formatNum(r.varIrr, 4) : "—") +
          "</td></tr>"
      )
      .join("");
    tbl.innerHTML = head + body + "</tbody>";
  }

  function renderResults(data, hurdleDec) {
    lastRawResult = data;
    document.getElementById("resultsWrap").hidden = false;
    const rawOut = document.getElementById("rawOut");
    if (rawOut) rawOut.textContent = JSON.stringify(data, null, 2);

    const m = data.metrics || {};
    const dscr = m.dscr || {};
    const irr = m.irr_annual;
    const covenant = lastRunContext.covenantDscr;

    renderKpiRow(m, covenant, hurdleDec, data.metadata && data.metadata.n_scenarios);
    renderPseudoHistogram(
      "histDscr",
      dscr,
      (x) => formatNum(x, 3),
      "DSCR (coverage ratio)"
    );
    renderPseudoHistogram(
      "histIrr",
      irr,
      (x) => (100 * x).toFixed(1) + "%",
      "IRR (% per year)"
    );
    renderPseudoHistogram(
      "histCapex",
      m.total_capex,
      (x) => formatNum(x, 0),
      "Total CAPEX (model currency)"
    );

    renderDscrCovenantBand(dscr, covenant);
    renderIrrBandChart(irr, hurdleDec);
  }

  async function simulateOnce(statusEl) {
    const n = readNum("nScenarios", 2500);
    const seed = readNum("seed", 42);
    const yahoo = document.getElementById("yahooCopper").checked;
    const yahooSymbol = document.getElementById("yahooSymbol").value;
    const yahooPeriod = document.getElementById("yahooPeriod").value;
    const yahooDaysEl = document.getElementById("yahooHistoryDays");
    const yahooHistoryDaysRaw = yahooDaysEl && yahooDaysEl.value.trim() !== "" ? yahooDaysEl.value : null;
    const shocks = parseShockInputs();

    const baseAsset = buildAssetFromInvestorForm();
    syncJsonPreview(buildAssetWithShocks(baseAsset, shocks));
    const asset = buildAssetWithShocks(baseAsset, shocks);
    const shockpack = buildShockpack(n, seed, yahoo, yahooSymbol, yahooPeriod, yahooHistoryDaysRaw);

    const hurdleDec = readNum("invHurdlePct", 8) / 100;

    const headers = { "Content-Type": "application/json" };
    if (API_KEY) headers["X-API-Key"] = API_KEY;

    const nNum = Number(n);
    const performance_profile = nNum > 5000 ? "standard" : "interactive";

    const res = await fetch("/v1/simulate/asset", {
      method: "POST",
      headers,
      body: JSON.stringify({
        shockpack,
        asset,
        include_attribution: false,
        performance_profile,
      }),
    });
    const text = await res.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch {
      throw new Error(text.slice(0, 200) || res.statusText);
    }
    if (!res.ok) {
      const detail = data.detail || JSON.stringify(data);
      const msg = typeof detail === "string" ? detail : JSON.stringify(detail);
      if (res.status === 401) {
        throw new Error(
          "Unauthorized (401). Check API_KEY in app.js vs server .env; open from same host as API."
        );
      }
      throw new Error(`${res.status}: ${msg}`);
    }

    lastRunContext = {
      covenantDscr:
        asset.financing?.covenant_dscr ??
        asset.financing?.covenantDscr ??
        lastRunContext.covenantDscr ??
        1.2,
    };
    renderResults(data, hurdleDec);
    return data;
  }

  async function runSimulation() {
    renderCompareTable([]);
    const status = document.getElementById("status");
    status.textContent = "";
    status.classList.remove("err");
    status.textContent = "Running…";
    try {
      await simulateOnce(status);
      status.textContent = "Done.";
    } catch (e) {
      status.textContent = "Error: " + e.message;
      status.classList.add("err");
    }
  }

  async function runCopperLadder() {
    const status = document.getElementById("status");
    status.textContent = "";
    status.classList.remove("err");
    const steps = [
      { name: "Base (no extra CAPEX shock)", pct: 0 },
      { name: "Copper / materials +5%", pct: 5 },
      { name: "Copper / materials +10%", pct: 10 },
      { name: "Copper / materials +15%", pct: 15 },
    ];
    const hurdleDec = readNum("invHurdlePct", 8) / 100;
    status.textContent = "Running copper ladder…";
    const rows = [];
    try {
      for (const s of steps) {
        syncScenarioSliders({ capexPct: s.pct, opexPct: readNum("opexPct", 0), rateBps: readNum("rateBps", 0) });
        const data = await simulateOnce(status);
        const m = data.metrics;
        const irr = m.irr_annual;
        rows.push({
          name: s.name,
          capexPct: s.pct,
          pBreach: m.covenant_breach_probability,
          pIrr: estimatePIrrBelowHurdle(irr, hurdleDec),
          p95Capex: m.total_capex && m.total_capex.p95,
          varIrr: m.var_irr_95,
        });
      }
      renderCompareTable(rows);
      status.textContent = "Copper ladder done — table below; last run = highest shock.";
    } catch (e) {
      status.textContent = "Error: " + e.message;
      status.classList.add("err");
    }
  }

  function bindRangeNumber(rangeId, numId, snapStep) {
    const r = document.getElementById(rangeId);
    const n = document.getElementById(numId);
    if (!r || !n) return;
    const min = Number(r.min);
    const max = Number(r.max);
    function clampRound(v) {
      let x = Math.min(max, Math.max(min, v));
      if (snapStep != null && snapStep > 0) {
        x = Math.round(x / snapStep) * snapStep;
        x = Math.min(max, Math.max(min, x));
      }
      return x;
    }
    r.addEventListener("input", () => {
      n.value = r.value;
      updateScenarioHint();
    });
    n.addEventListener("input", () => {
      const raw = parseFloat(n.value);
      if (!Number.isFinite(raw)) {
        updateScenarioHint();
        return;
      }
      const v = clampRound(raw);
      n.value = String(v);
      r.value = String(v);
      updateScenarioHint();
    });
  }

  function setActiveScenarioTab(id) {
    document.querySelectorAll(".scenario-tab").forEach((b) => {
      b.classList.toggle("scenario-tab--active", b.dataset.scenario === id);
    });
  }

  document.getElementById("runBtn").addEventListener("click", runSimulation);
  const compareBtn = document.getElementById("compareCopperBtn");
  if (compareBtn) compareBtn.addEventListener("click", runCopperLadder);

  document.querySelectorAll(".scenario-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.scenario;
      if (!id || !SCENARIO_PRESETS[id]) return;
      syncScenarioSliders(SCENARIO_PRESETS[id]);
      setActiveScenarioTab(id);
    });
  });

  bindRangeNumber("capexPctRange", "capexPct", null);
  bindRangeNumber("opexPctRange", "opexPct", null);
  bindRangeNumber("rateBpsRange", "rateBps", 25);

  function syncYahooPanel() {
    const on = document.getElementById("yahooCopper").checked;
    const panel = document.getElementById("yahooPanel");
    if (panel) panel.classList.toggle("yahoo-panel--disabled", !on);
    const ys = document.getElementById("yahooSymbol");
    const yp = document.getElementById("yahooPeriod");
    const yd = document.getElementById("yahooHistoryDays");
    if (ys) ys.disabled = !on;
    if (yp) yp.disabled = !on;
    if (yd) yd.disabled = !on;
  }

  document.getElementById("yahooCopper").addEventListener("change", syncYahooPanel);

  const hurdleEl = document.getElementById("invHurdlePct");
  if (hurdleEl) {
    hurdleEl.addEventListener("input", () => {
      if (!lastRawResult) return;
      renderResults(lastRawResult, readNum("invHurdlePct", 8) / 100);
    });
  }

  /** Populate form from defaults */
  const invDefaults = {
    invRevenue: 42e6,
    invOpex: 18e6,
    invUtilityOpex: 7.2e6,
    invCapex: 280e6,
    invEquityPct: 35,
    invCoupon: 6.5,
    invTerm: 18,
    invCovenant: 1.2,
    invHurdlePct: 8,
    invHorizon: 15,
    invAssetId: "dc-fra-01",
  };
  Object.keys(invDefaults).forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.value = String(invDefaults[id]);
  });

  syncJsonPreview(buildAssetWithShocks(buildAssetFromInvestorForm(), parseShockInputs()));
  setActiveScenarioTab("base");
  syncScenarioSliders(SCENARIO_PRESETS.base);
  syncYahooPanel();
  updateScenarioHint();
})();
