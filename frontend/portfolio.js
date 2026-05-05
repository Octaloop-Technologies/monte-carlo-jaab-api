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

  function randInt(lo, hiInclusive) {
    return lo + Math.floor(Math.random() * (hiInclusive - lo + 1));
  }

  function randFloat(lo, hi) {
    return lo + Math.random() * (hi - lo);
  }

  /**
   * Fill the form with reproducible-random economics and shock settings (still need Run).
   * Correlation heat-maps and KPIs change meaningfully because σ, ρ, copula, counts, and balance sheets move.
   */
  function randomizePortfolioInputs() {
    const pfIde = document.getElementById("pfId");
    const pfAse = document.getElementById("pfAsId");
    if (pfIde) pfIde.value = "random-pool-" + randInt(100, 999999);
    if (pfAse) pfAse.value = "asof-rnd-" + randInt(100, 999999);

    const set = (id, v) => {
      const el = document.getElementById(id);
      if (el) el.value = String(v);
    };

    set("nScenarios", randInt(900, 4900));
    set("seed", randInt(1, 2_000_000_000));

    set("sigmaRev", randFloat(0.045, 0.14).toFixed(3));
    set("sigmaCapex", randFloat(0.035, 0.11).toFixed(3));
    set("sigmaOpex", randFloat(0.035, 0.1).toFixed(3));
    set("sigmaRate", randFloat(0.0015, 0.012).toFixed(4));

    const copEl = document.getElementById("copulaKind");
    if (copEl) copEl.value = Math.random() < 0.42 ? "student_t" : "gaussian";
    set("copulaDf", randFloat(3.5, 18).toFixed(1));

    const flip = Math.random();
    if (flip < 0.22) applyCorrPreset("independent");
    else if (flip < 0.45) applyCorrPreset("engine_default");
    else if (flip < 0.68) applyCorrPreset("high_joint");
    else {
      const sel = document.getElementById("corrPreset");
      if (sel) sel.value = "custom";
      for (const cid of CORR_PAIR_IDS) {
        const el = document.getElementById(cid);
        if (el) el.value = clampCorr(randFloat(-0.55, 0.88)).toFixed(2);
      }
    }

    const ycb = document.getElementById("yahooCopper");
    if (ycb) {
      ycb.checked = false;
      ycb.dispatchEvent(new Event("change"));
    }

    const nAssets = randInt(2, 4);
    const numSel = document.getElementById("numAssets");
    if (numSel) numSel.value = String(nAssets);
    renderAssetBlocks();

    for (let slot = 1; slot <= nAssets; slot++) {
      const rev = randFloat(22e6, 55e6);
      const maxOpex = rev * 0.46;
      let opex = randFloat(5e6, Math.max(6e6, maxOpex));
      opex = Math.min(opex, maxOpex);
      const capex = randFloat(92e6, 310e6);
      const eqPct = randInt(24, 54);
      const coupon = randFloat(5.35, 8.25);
      const term = randInt(11, 21);
      const cov = randFloat(1.12, 1.42);
      const hz = randInt(11, 21);
      const util =
        Math.random() < 0.35 ? randFloat(0, Math.min(opex * 0.15, 3.5e6)) : 0;

      const aid = document.getElementById("a" + slot + "_id");
      if (aid) aid.value = "asset-" + slot + "-" + randInt(100, 99999);

      set("a" + slot + "_rev", Math.round(rev));
      set("a" + slot + "_opex", Math.round(opex));
      set("a" + slot + "_capex", Math.round(capex));
      set("a" + slot + "_eq", eqPct);
      set("a" + slot + "_debt", "");
      set("a" + slot + "_coupon", coupon.toFixed(2));
      set("a" + slot + "_term", term);
      set("a" + slot + "_cov", cov.toFixed(2));
      set("a" + slot + "_hz", hz);
      set("a" + slot + "_util", Math.round(util));
    }

    trySyncRequestPreview();
  }

  /** Defaults on load: 3 named renewables-style assets, stronger macro ρ preset, vols — yields rich correlation tables after Run. */
  function trySyncRequestPreview() {
    try {
      const n = parseInt(document.getElementById("numAssets").value, 10) || 2;
      const assets = collectAssets(n);
      const shockpack = buildShockpack();
      syncRequestPreview({
        portfolio_id: (document.getElementById("pfId").value || "portfolio").trim(),
        portfolio_assumption_set_id: (document.getElementById("pfAsId").value || "asof").trim(),
        assets,
        shockpack,
      });
    } catch (e) {
      const ta = document.getElementById("reqJson");
      if (ta) ta.value = "// Request preview: " + e.message;
    }
  }

  function applySamplePortfolioPrefill() {
    const pfId = document.getElementById("pfId");
    const pfAs = document.getElementById("pfAsId");
    if (pfId) pfId.value = "sample-renewables-pool";
    if (pfAs) pfAs.value = "demo-2026-correlation";

    const numSel = document.getElementById("numAssets");
    if (numSel) numSel.value = "3";

    const set = (id, v) => {
      const el = document.getElementById(id);
      if (el) el.value = String(v);
    };
    set("nScenarios", "2500");
    set("seed", "11");
    set("sigmaRev", "0.09");
    set("sigmaCapex", "0.065");
    set("sigmaOpex", "0.055");
    set("sigmaRate", "0.006");

    const cop = document.getElementById("copulaKind");
    if (cop) cop.value = "gaussian";
    set("copulaDf", "8");

    const preset = document.getElementById("corrPreset");
    if (preset) preset.value = "high_joint";

    renderAssetBlocks();
    applyCorrPreset("high_joint");

    const ycb = document.getElementById("yahooCopper");
    if (ycb) {
      ycb.checked = false;
      ycb.dispatchEvent(new Event("change"));
    }

    trySyncRequestPreview();
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

  const FACTOR_DISPLAY = {
    revenue: "Revenue / FX",
    capex: "Capex / materials",
    opex: "Opex / energy · CPI",
    rate: "Interest rate",
  };

  function factorRowLabel(id) {
    return FACTOR_DISPLAY[id] || id;
  }

  function corrHeatBackground(r) {
    if (r == null || Number.isNaN(Number(r))) return "#353b43";
    const x = Math.max(-1, Math.min(1, Number(r)));
    const amp = Math.abs(x);
    if (amp < 0.03) return "#3d4554";
    if (x > 0) return `hsl(158, ${46 + amp * 38}%, ${24 + amp * 22}%)`;
    return `hsl(274, ${40 + amp * 45}%, ${24 + amp * 18}%)`;
  }

  function abbrevLabel(lbl, maxLen) {
    const s = String(lbl || "");
    if (s.length <= maxLen) return s;
    return s.slice(0, Math.max(0, maxLen - 1)) + "…";
  }

  function isSquareCorrelationMatrix(labels, mat) {
    const n = labels.length;
    if (!mat || mat.length !== n) return false;
    return mat.every((row) => row && row.length === n);
  }

  function buildCorrelationDataTable(labels, mat) {
    if (!isSquareCorrelationMatrix(labels, mat)) return "";
    let h =
      '<table class="data data--corr-mx"><thead><tr><th></th>';
    for (const id of labels) {
      h += '<th scope="col">' + escapeAttr(id) + "</th>";
    }
    h += "</tr></thead><tbody>";
    for (let i = 0; i < mat.length; i++) {
      h += '<tr><th scope="row">' + escapeAttr(labels[i] || "") + "</th>";
      const row = mat[i] || [];
      for (let j = 0; j < row.length; j++) {
        const v = row[j];
        h += "<td>" + (v == null || Number.isNaN(v) ? "—" : fmtNum(v, 3)) + "</td>";
      }
      h += "</tr>";
    }
    h += "</tbody></table>";
    return h;
  }

  /**
   * Color heat-map of ρ plus optional collapsible numeric table (no canvas).
   */
  function buildCorrelationHeatmapBlock(title, labels, mat, numericSummaryLabel) {
    if (!isSquareCorrelationMatrix(labels, mat)) return "";
    const n = labels.length;

    let h =
      '<div class="corr-heatmap-block">' +
      '<h4 class="corr-mx-title">' +
      escapeAttr(title) +
      "</h4>" +
      '<div class="corr-heatmap-scroll">' +
      '<div class="corr-heatmap" style="--corr-n:' +
      n +
      '" role="grid" aria-label="' +
      escapeAttr(title) +
      '">';
    h += '<div class="corr-heatmap-corner" aria-hidden="true"></div>';
    for (let j = 0; j < n; j++) {
      const lbl = labels[j];
      h +=
        '<div class="corr-heatmap-colhead" role="columnheader" title="' +
        escapeAttr(lbl) +
        '">' +
        escapeAttr(abbrevLabel(lbl, 12)) +
        "</div>";
    }
    for (let i = 0; i < n; i++) {
      const ri = labels[i];
      h +=
        '<div class="corr-heatmap-rowhead" role="rowheader" title="' +
        escapeAttr(ri) +
        '">' +
        escapeAttr(abbrevLabel(ri, 14)) +
        "</div>";
      const row = mat[i] || [];
      for (let j = 0; j < n; j++) {
        const v = row[j];
        const num = v == null || Number.isNaN(Number(v)) ? null : Number(v);
        const txt = num == null ? "—" : fmtNum(num, 3);
        const bg = corrHeatBackground(num);
        const cellCls =
          num == null ? "corr-heatmap-cell corr-heatmap-cell--na" : "corr-heatmap-cell";
        const tip =
          num == null ? "missing" : "Pearson correlation ρ = " + txt;
        h +=
          '<div class="' +
          cellCls +
          '" role="gridcell" title="' +
          escapeAttr(tip) +
          '" style="background-color:' +
          bg +
          '"><span class="corr-heatmap-num">' +
          txt +
          "</span></div>";
      }
    }
    h +=
      "</div></div>" +
      '<p class="corr-heatmap-legend"><span class="corr-leg-cap">Pearson ρ</span>' +
      '<span class="corr-leg-track"><span>-1</span><span class="corr-leg-bar" role="presentation"></span><span>+1</span></span>' +
      '<span class="corr-leg-caption">Tone: violet = negative linkage · muted = ~0 · teal = positive</span></p>';

    const tbl = buildCorrelationDataTable(labels, mat);
    if (tbl) {
      const sumLabel = numericSummaryLabel || "Numeric ρ table";
      h +=
        '<details class="corr-numeric-details"><summary>' +
        escapeAttr(sumLabel) +
        '</summary><div class="table-wrap">' +
        tbl +
        "</div></details>";
    }
    h += "</div>";
    return h;
  }

  function getOrCreateCorrPanel() {
    let wrap = document.getElementById("pfCorrPanel");
    if (wrap) return wrap;
    const assetPanel = document.getElementById("pfAssetTable")?.closest(".results-panel");
    if (!assetPanel || !assetPanel.parentNode) return null;
    wrap = document.createElement("div");
    wrap.id = "pfCorrPanel";
    wrap.className = "results-panel results-panel--wide pf-corr-panel";
    wrap.setAttribute("aria-live", "polite");
    assetPanel.parentNode.insertBefore(wrap, assetPanel.nextSibling);
    return wrap;
  }

  function renderCorrelationSection(portfolio, meta) {
    const wrap = getOrCreateCorrPanel();
    if (!wrap) return;

    const fo = (meta && meta.factor_order) || [];
    const fc = (meta && meta.factor_correlation) || [];
    const hasMacro =
      fc.length > 0 &&
      fo.length === fc.length &&
      fc.every((row) => row && row.length === fo.length);

    const chunks = [];

    if (hasMacro) {
      const labels = fo.map(factorRowLabel);
      const cop =
        meta && meta.copula
          ? '<p class="results-caption corr-copula-note">Copula: <code>' +
            escapeAttr(String(meta.copula)) +
            "</code></p>"
          : "";
      chunks.push(
        '<h3 class="results-heading">Macro drivers — factor correlation (input)</h3>' +
          '<p class="results-caption">' +
          "Pearson ρ between <strong>joint shock draws</strong> for the drivers in your shock pack (section 2). " +
          "<strong>Tile colour</strong> encodes ρ; hover a cell or open the numeric table.</p>" +
          cop +
          '<div class="corr-matrix-grid corr-matrix-grid--single">' +
          buildCorrelationHeatmapBlock("Macro factors × factors", labels, fc, "Numeric ρ (macro)") +
          "</div>"
      );
    } else {
      chunks.push(
        '<h3 class="results-heading">Macro drivers — factor correlation</h3>' +
          '<p class="results-caption results-caption--warn">' +
          "No <code>metadata.factor_correlation</code> in this response — restart the API from the latest code, or inspect Raw JSON.</p>"
      );
    }

    const assetIds = (meta && meta.asset_ids) || [];
    const d = portfolio && portfolio.cross_asset_dscr_correlation_pearson;
    const ir = portfolio && portfolio.cross_asset_equity_irr_correlation_pearson;

    if (isSquareCorrelationMatrix(assetIds, d)) {
      chunks.push(
        '<hr class="corr-divider" />' +
          '<h3 class="results-heading">Cross-asset — outcome correlation (output)</h3>' +
          '<p class="results-caption">' +
          "Pearson ρ of path <strong>DSCR</strong> and path <strong>IRR</strong> between sites — same Monte Carlo row = same macro world. Colour = strength of co-movement.</p>" +
          '<p class="results-caption results-caption--tight">' +
          "Portfolio-wide tiles: <strong>min / blend / max</strong> DSCR are three ways to aggregate each Monte Carlo path (weakest asset, revenue-weighted average, strongest asset). <strong>Blend equity IRR</strong> uses the same revenue weights — it is not the IRR of pooled cashflows as one project.</p>" +
          '<div class="corr-matrix-grid">' +
          buildCorrelationHeatmapBlock("DSCR × DSCR", assetIds, d, "Numeric ρ — DSCR") +
          (isSquareCorrelationMatrix(assetIds, ir)
            ? buildCorrelationHeatmapBlock("IRR × IRR", assetIds, ir, "Numeric ρ — IRR")
            : "") +
          "</div>"
      );
    } else if (!d || !d.length) {
      chunks.push(
        '<hr class="corr-divider" />' +
          '<h3 class="results-heading">Cross-asset — outcome correlation</h3>' +
          '<p class="results-caption results-caption--warn">' +
          "No <code>portfolio.cross_asset_dscr_correlation_pearson</code> in this response — restart API from latest code.</p>"
      );
    } else {
      chunks.push(
        '<hr class="corr-divider" />' +
          '<h3 class="results-heading">Cross-asset — outcome correlation</h3>' +
          '<p class="results-caption results-caption--warn">' +
          "Correlation matrix shape does not match <code>asset_ids</code>; check Raw JSON.</p>"
      );
    }
    wrap.hidden = false;
    wrap.style.removeProperty("display");
    wrap.innerHTML = chunks.join("");
  }

  function renderPortfolioKpis(portfolio, meta) {
    const row = document.getElementById("pfKpiRow");
    if (!row || !portfolio) return;

    const minD = portfolio.min_dscr_across_assets || {};
    const blendD = portfolio.revenue_weighted_mean_dscr_across_assets || {};
    const blendI = portfolio.revenue_weighted_mean_equity_irr_across_assets || {};
    const maxD = portfolio.max_dscr_across_assets || {};
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
        k: "Min DSCR — pool (p50)",
        v: minD.p50 != null ? fmtNum(minD.p50, 3) : "—",
        sub: "Weakest name each path, then median",
      },
      {
        k: "Blend DSCR — pool (p50)",
        v: blendD.p50 != null ? fmtNum(blendD.p50, 3) : "—",
        sub: "Revenue-weighted mean of asset DSCRs each path (see API)",
      },
      {
        k: "Max DSCR — pool (p50)",
        v: maxD.p50 != null ? fmtNum(maxD.p50, 3) : "—",
        sub: "Strongest name each path, then median",
      },
      {
        k: "Blend equity IRR (p50)",
        v: blendI.p50 != null ? fmtNum(100 * blendI.p50, 2) + "%" : "—",
        sub: "Revenue-weighted IRR paths — not fund-level IRR",
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

    const sorted = [...perAsset].sort((a, b) =>
      String(a.asset_id || "").localeCompare(String(b.asset_id || ""), undefined, { sensitivity: "base" })
    );

    const head =
      "<thead><tr><th scope=\"col\">Asset</th><th scope=\"col\">P(breach)</th><th scope=\"col\">DSCR p50</th><th scope=\"col\">IRR p50</th><th scope=\"col\">PD proxy</th></tr></thead><tbody>";
    const body = sorted
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
    renderCorrelationSection(portfolio, meta);

    const minD = portfolio.min_dscr_across_assets;
    const blendHist = portfolio.revenue_weighted_mean_dscr_across_assets;
    renderPseudoHistogram(
      "pfHistMinDscr",
      minD,
      (x) => fmtNum(x, 3),
      "Min DSCR (worst asset per scenario)"
    );
    renderPseudoHistogram(
      "pfHistBlendDscr",
      blendHist,
      (x) => fmtNum(x, 3),
      "Blend DSCR (revenue-weighted mean per scenario)"
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
      num.addEventListener("change", () => {
        renderAssetBlocks();
        trySyncRequestPreview();
      });
    }
    bindCorrelationControls();
    applySamplePortfolioPrefill();

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

    const rnd = document.getElementById("randomizePfBtn");
    if (rnd) {
      rnd.addEventListener("click", () => {
        const status = document.getElementById("pfStatus");
        randomizePortfolioInputs();
        if (status) {
          status.textContent = "Random inputs applied — click Run portfolio simulation.";
          status.classList.remove("err");
        }
      });
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
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();
