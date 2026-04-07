/**
 * V0 scenario lab — builds payloads for POST /v1/simulate/asset.
 * User-defined % shifts: CAPEX (copper/materials), OPEX (power/CPI), rate (bps).
 * Optional Yahoo HG=F calibrates capex_log_sigma.
 */
(function () {
  const API_KEY = "5hm4R9Rlj0x2sCresLa038nAeOQyU8LgDT-HHfJTrns";
  const DEFAULT_ASSET = {
    asset_id: "dc-fra-01",
    assumption_set_id: "frontend-v0",
    horizon_years: 15,
    base_revenue_annual: 42e6,
    base_opex_annual: 18e6,
    utility_opex_annual: 7.2e6,
    initial_capex: 280e6,
    equity_fraction: 0.35,
    tax_rate: 0.0,
    financing: {
      debt_principal: 182e6,
      interest_rate_annual: 0.065,
      loan_term_years: 18,
      covenant_dscr: 1.2,
    },
  };

  const multMin = 0.05;
  const multMax = 5.0;
  const rateCap = 0.45;

  /** Last successful run (for “vs previous”) — updated only on new simulation. */
  let previousSnapshot = null;
  /** Covenant threshold from last request (not in API response). */
  let lastRunContext = { covenantDscr: 1.2 };

  function deepCopy(obj) {
    return JSON.parse(JSON.stringify(obj));
  }

  function parseShockInputs() {
    const capexPct = Number(document.getElementById("capexPct").value);
    const opexPct = Number(document.getElementById("opexPct").value);
    const rateBps = Number(document.getElementById("rateBps").value);
    return {
      capexPct: Number.isFinite(capexPct) ? capexPct : 0,
      opexPct: Number.isFinite(opexPct) ? opexPct : 0,
      rateBps: Number.isFinite(rateBps) ? rateBps : 0,
    };
  }

  /**
   * Keep range slider and number field in sync; optional snapStep for bps (25).
   */
  function bindRangeNumber(rangeId, numId, snapStep) {
    const r = document.getElementById(rangeId);
    const n = document.getElementById(numId);
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
      updateShockSummary();
    });

    n.addEventListener("input", () => {
      const raw = parseFloat(n.value);
      if (!Number.isFinite(raw)) {
        updateShockSummary();
        return;
      }
      const v = clampRound(raw);
      n.value = String(v);
      r.value = String(v);
      updateShockSummary();
    });
  }

  function updateShockSummary() {
    const { capexPct, opexPct, rateBps } = parseShockInputs();
    const cx = 1 + capexPct / 100;
    const ox = 1 + opexPct / 100;
    const rateAdj = rateBps / 10000;
    const parts = [];
    if (capexPct !== 0) {
      parts.push(
        `CAPEX path ×${cx.toFixed(4)} (${capexPct >= 0 ? "+" : ""}${capexPct}% vs base)`
      );
    }
    if (opexPct !== 0) {
      parts.push(
        `OPEX path ×${ox.toFixed(4)} (${opexPct >= 0 ? "+" : ""}${opexPct}% vs base)`
      );
    }
    if (rateBps !== 0) {
      parts.push(
        `coupon +${rateBps} bps (${rateAdj >= 0 ? "+" : ""}${(rateAdj * 100).toFixed(2)}% p.a. absolute)`
      );
    }
    let yahooLine = "";
    if (document.getElementById("yahooCopper").checked) {
      const sym = document.getElementById("yahooSymbol").value.trim() || "HG=F";
      const per = document.getElementById("yahooPeriod").value || "1y";
      yahooLine = ` CAPEX vol from Yahoo: ${sym} · ${per}.`;
    }
    const el = document.getElementById("shockSummary");
    if (parts.length === 0 && !yahooLine) {
      el.textContent =
        "No level shocks: Monte Carlo uses the JSON baseline only (random draws on all factors).";
    } else {
      const level =
        parts.length > 0
          ? "Level shocks on top of draws: " + parts.join(" · ") + "."
          : "No extra level shocks.";
      el.textContent = level + yahooLine;
    }
  }

  function assetFromForm() {
    const raw = document.getElementById("assetJson").value;
    return JSON.parse(raw);
  }

  function baseShockpack(n, seed, useYahoo, yahooSymbol, yahooPeriod) {
    const sp = {
      shockpack_id: "frontend-v0",
      seed: Number(seed),
      n_scenarios: Number(n),
      sampling_method: "monte_carlo",
    };
    if (useYahoo) {
      const symbol = (yahooSymbol || "").trim() || "HG=F";
      const period = (yahooPeriod || "1y").trim() || "1y";
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

  /**
   * Apply user % to level multipliers and bps to coupon.
   */
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

  function row(tbl, k, v) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${k}</td><td>${v}</td>`;
    tbl.appendChild(tr);
  }

  function formatPct(x) {
    if (x == null || Number.isNaN(x)) return "—";
    return (100 * x).toFixed(2) + "%";
  }

  function formatNum(x, d = 4) {
    if (x == null || Number.isNaN(x)) return "—";
    return Number(x).toFixed(d);
  }

  const PLAIN_BAR = {
    p05: { short: "p5", plain: "Rough" },
    p10: { short: "p10", plain: "Weak" },
    p50: { short: "p50", plain: "Typical" },
    p90: { short: "p90", plain: "Strong" },
    p95: { short: "p95", plain: "Very strong" },
  };

  function renderBars(containerId, summary) {
    const el = document.getElementById(containerId);
    el.innerHTML = "";
    if (!summary) {
      el.textContent = "—";
      return;
    }
    const keys = ["p05", "p10", "p50", "p90", "p95"];
    const vals = keys.map((k) => summary[k]).filter((v) => v != null && Number.isFinite(v));
    if (!vals.length) {
      el.textContent = "—";
      return;
    }
    const lo = Math.min(...vals);
    const hi = Math.max(...vals);
    const span = Math.max(hi - lo, 1e-9);
    keys.forEach((key) => {
      const v = summary[key];
      if (v == null || !Number.isFinite(v)) return;
      const meta = PLAIN_BAR[key] || { short: key, plain: key };
      const h = 35 + 65 * ((v - lo) / span);
      const bar = document.createElement("div");
      bar.className = "bar";
      bar.style.height = `${h}%`;
      bar.style.opacity =
        key === "p50" ? "1" : key === "p10" ? "0.88" : "0.75";
      bar.innerHTML =
        '<span class="val">' +
        formatNum(v, 3) +
        '</span><span class="bar-plain">' +
        meta.plain +
        '</span><span class="bar-tech">' +
        meta.short +
        "</span>";
      el.appendChild(bar);
    });
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

  function trafficCell(status, title, hint) {
    const verdict = { ok: "Comfortable", warn: "Caution", bad: "Pressure" };
    return (
      '<div class="traffic-cell traffic-cell--' +
      status +
      '"><span class="traffic-dot" aria-hidden="true"></span><div class="traffic-text"><strong>' +
      title +
      "</strong><span>" +
      hint +
      '</span><em class="traffic-verdict">' +
      verdict[status] +
      "</em></div></div>"
    );
  }

  function buildPlainHeadline(loan, rule, ret) {
    const opening =
      rule === "bad" || loan === "bad"
        ? "This picture looks <strong>high-pressure</strong> for the loan and owners."
        : rule === "warn" || loan === "warn" || ret === "warn"
          ? "This picture is <strong>mixed</strong>: the middle case may be fine, but bad years deserve attention."
          : "This picture looks <strong>relatively calm</strong> at a glance — still confirm with your own risk standards.";

    const returns =
      ret === "bad"
        ? " Investor losses show up in rough simulations."
        : ret === "warn"
          ? " Investor returns can undershoot expectations when luck is poor."
          : " Rough simulations still show tolerable returns for investors.";

    return opening + returns;
  }

  function buildDscrChips(dscr, cov) {
    if (!dscr || dscr.p05 == null || dscr.p50 == null || dscr.p95 == null) {
      return '<p class="chart-empty">No loan-coverage numbers in this response.</p>';
    }
    const covOk = Number.isFinite(cov);
    const covStr = covOk ? formatNum(cov, 2) : "—";
    const under =
      covOk && dscr.p05 < cov
        ? "Dips below the bank’s minimum in this rough year."
        : covOk
          ? "Still at or above the bank’s minimum in this rough year."
          : "Rough year in the simulation (higher DSCR is safer).";
    return (
      '<div class="outcome-chip outcome-chip--stress"><span class="outcome-label">Rough year</span><span class="outcome-val">' +
      formatNum(dscr.p05, 2) +
      '</span><span class="outcome-hint">' +
      under +
      '</span></div><div class="outcome-chip outcome-chip--mid"><span class="outcome-label">Typical year</span><span class="outcome-val">' +
      formatNum(dscr.p50, 2) +
      '</span><span class="outcome-hint">Middle of the pack — half ' +
      "the runs are better, half are worse.</span></div>" +
      '<div class="outcome-chip outcome-chip--sun"><span class="outcome-label">Strong year</span><span class="outcome-val">' +
      formatNum(dscr.p95, 2) +
      '</span><span class="outcome-hint">A strong cash year (bank minimum is ' +
      covStr +
      ").</span></div>"
    );
  }

  function buildIrrChips(irr, hurdle) {
    if (!irr || irr.p05 == null || irr.p50 == null || irr.p95 == null) {
      return '<p class="chart-empty">No investor-return (IRR) numbers in this response.</p>';
    }
    const pct = (x) => (100 * x).toFixed(1) + "% per year";
    let stressHint = "Still positive even in a rough draw.";
    if (irr.p05 < 0) stressHint = "Negative in this rough draw (losing money on that path).";
    else if (hurdle != null && Number.isFinite(hurdle) && irr.p05 < hurdle)
      stressHint =
        "Below your target return in this rough draw (target " +
        (100 * hurdle).toFixed(1) +
        "%/yr).";

    const targetHint =
      hurdle != null && Number.isFinite(hurdle)
        ? "Your typed target is " + (100 * hurdle).toFixed(1) + "% per year."
        : "Add a hurdle under results to compare to a target return.";

    return (
      '<div class="outcome-chip outcome-chip--stress"><span class="outcome-label">Rough patch</span><span class="outcome-val">' +
      pct(irr.p05) +
      '</span><span class="outcome-hint">' +
      stressHint +
      '</span></div><div class="outcome-chip outcome-chip--mid"><span class="outcome-label">Typical</span><span class="outcome-val">' +
      pct(irr.p50) +
      '</span><span class="outcome-hint">Like an “expected” yearly return in the middle.</span></div>' +
      '<div class="outcome-chip outcome-chip--sun"><span class="outcome-label">Strong run</span><span class="outcome-val">' +
      pct(irr.p95) +
      '</span><span class="outcome-hint">' +
      targetHint +
      "</span></div>"
    );
  }

  function renderPlainLanguageBlock(m, dscr, irr, covenant) {
    const story = document.getElementById("plainStoryBody");
    const dscrEl = document.getElementById("simpleDscrBody");
    const irrEl = document.getElementById("simpleIrrBody");
    const breach = m.covenant_breach_probability;
    const cov = Number(covenant);

    let loanStatus = "ok";
    if (dscr.p05 != null && dscr.p50 != null && Number.isFinite(cov)) {
      if (dscr.p05 < cov) loanStatus = dscr.p50 < cov ? "bad" : "warn";
    } else if (dscr.p05 != null && Number.isFinite(cov) && dscr.p05 < cov) {
      loanStatus = "warn";
    }

    let ruleStatus = "ok";
    if (breach != null && Number.isFinite(breach)) {
      if (breach > 0.35) ruleStatus = "bad";
      else if (breach > 0.15) ruleStatus = "warn";
    }

    let returnStatus = "ok";
    const hRaw = document.getElementById("hurdle").value.trim();
    const hurdle = hRaw !== "" && !Number.isNaN(Number(hRaw)) ? Number(hRaw) : null;
    if (irr && irr.p05 != null && irr.p50 != null) {
      if (irr.p05 < 0) returnStatus = irr.p50 < 0 ? "bad" : "warn";
      if (hurdle != null && irr.p05 < hurdle) {
        returnStatus = returnStatus === "bad" ? "bad" : "warn";
      }
    }

    const headline = buildPlainHeadline(loanStatus, ruleStatus, returnStatus);

    story.innerHTML =
      '<p class="plain-story-lede">' +
      headline +
      '</p><div class="traffic-grid">' +
      trafficCell(
        loanStatus,
        "Cash cushion vs the loan",
        "Do rough years still show enough cash compared with debt payments?"
      ) +
      trafficCell(
        ruleStatus,
        "Loan rule breaks",
        "Out of many fake futures, how often do we break the bank’s minimum?"
      ) +
      trafficCell(
        returnStatus,
        "Owner returns in bad luck",
        "If the project has a bad run, do investors still get a bearable return?"
      ) +
      "</div>";

    dscrEl.innerHTML = buildDscrChips(dscr, cov);
    irrEl.innerHTML = buildIrrChips(irr, hurdle);
  }

  function renderRiskProbChart(m) {
    const el = document.getElementById("riskProbChart");
    const rows = [
      {
        plain: "Breaking the bank’s cash rule",
        tech: "Share of runs below covenant DSCR",
        v: m.covenant_breach_probability,
        cls: "hbar-fill--breach",
      },
      {
        plain: "Cash is extremely tight (under 1× cover)",
        tech: "Model shortcut for “can’t fully cover debt”",
        v: m.probability_of_default_proxy_dscr_lt_1,
        cls: "hbar-fill--pd",
      },
      {
        plain: "Extra “equity could be wiped” signal",
        tech: "Structural-style shorthand (not a rating)",
        v: m.merton_equity_pd_proxy,
        cls: "hbar-fill--merton",
      },
    ];
    el.innerHTML = rows
      .map((r) => {
        const p =
          r.v == null || !Number.isFinite(Number(r.v))
            ? null
            : Math.max(0, Math.min(1, Number(r.v)));
        const pct = p == null ? 0 : p * 100;
        const show = p == null ? "—" : pct.toFixed(1) + "%";
        return (
          '<div class="hbar-row"><span class="hbar-label"><span class="hbar-plain">' +
          r.plain +
          '</span><span class="hbar-tech">' +
          r.tech +
          '</span></span><div class="hbar-track"><div class="hbar-fill ' +
          r.cls +
          '" style="width:' +
          (p == null ? 0 : pct) +
          '%"></div></div><span class="hbar-val">' +
          show +
          "</span></div>"
        );
      })
      .join("");
  }

  function renderNamedBars(containerId, namedPairs) {
    const el = document.getElementById(containerId);
    el.innerHTML = "";
    const pts = namedPairs.filter(([, v]) => v != null && Number.isFinite(v));
    if (pts.length < 2) {
      el.innerHTML =
        '<p class="chart-empty">Not enough return numbers for this picture (need at least two of: rough patch, worst-5% average, typical, strong).</p>';
      return;
    }
    const vals = pts.map(([, v]) => v);
    const lo = Math.min(...vals);
    const hi = Math.max(...vals);
    const span = Math.max(hi - lo, 1e-9);
    pts.forEach(([label, v]) => {
      const h = 35 + 65 * ((v - lo) / span);
      const bar = document.createElement("div");
      bar.className = "bar";
      bar.style.height = `${h}%`;
      bar.style.opacity =
        label === "Typical (middle)"
          ? "1"
          : label.indexOf("Worst 5%") === 0
            ? "0.95"
            : "0.78";
      bar.innerHTML =
        '<span class="val">' +
        formatNum(v, 4) +
        "</span><span>" +
        label +
        "</span>";
      el.appendChild(bar);
    });
  }

  function renderCashDistributionBars(m) {
    const panel = document.getElementById("cashDistPanel");
    const ebitda = m.ebitda;
    const cf = m.levered_cf;
    renderBars("ebitdaDistBars", ebitda);
    renderBars("leveredCfDistBars", cf);
    const hasE =
      ebitda &&
      ["p05", "p10", "p50", "p90", "p95"].some(
        (k) => ebitda[k] != null && Number.isFinite(ebitda[k])
      );
    const hasC =
      cf &&
      ["p05", "p10", "p50", "p90", "p95"].some(
        (k) => cf[k] != null && Number.isFinite(cf[k])
      );
    panel.hidden = !hasE && !hasC;
  }

  function renderNavProxyBand(nav) {
    const el = document.getElementById("navBandChart");
    const panel = document.getElementById("navPanel");
    if (!nav || nav.p05 == null || nav.p95 == null || nav.p50 == null) {
      panel.hidden = true;
      el.innerHTML = "";
      return;
    }
    panel.hidden = false;
    const { lo, hi } = bandDomain([nav.p05, nav.p95]);
    const left = Math.max(0, Math.min(100, pctInDomain(nav.p05, lo, hi)));
    const right = Math.max(0, Math.min(100, pctInDomain(nav.p95, lo, hi)));
    const width = Math.max(1.5, right - left);
    const med = Math.max(0, Math.min(100, pctInDomain(nav.p50, lo, hi)));
    el.innerHTML =
      '<div class="h-band-axis"><span>' +
      formatNum(lo, 0) +
      "</span><span>" +
      formatNum(hi, 0) +
      '</span></div><div class="h-band-track">' +
      '<div class="h-band-range h-band-range--nav" style="left:' +
      left +
      "%;width:" +
      width +
      '%"></div>' +
      '<div class="h-band-median" style="left:' +
      med +
      '%" title="Median"></div></div>' +
      '<p class="h-band-legend">Wider band = less certainty about shareholder value at the end. Numbers use the same currency as your project inputs.</p>';
  }

  function renderDscrCovenantBand(dscr, covenantDscr) {
    const el = document.getElementById("dscrBandChart");
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
      '%" title="p05–p95"></div>' +
      '<div class="h-band-median" style="left:' +
      med +
      '%" title="Median"></div>' +
      '<div class="h-band-ref h-band-ref--bad" style="left:' +
      line +
      '%"><span>Covenant ' +
      formatNum(cov, 2) +
      "</span></div></div>" +
      '<p class="h-band-legend">Think of the <strong>left</strong> side of the green band as “bad luck years” and the <strong>right</strong> as “good luck.” If most of the green sits <strong>left of the red line</strong>, many simulated years can’t meet the bank’s minimum cash rule.</p>';
  }

  function renderIrrBandChart(irr) {
    const el = document.getElementById("irrBandChart");
    if (!irr || irr.p05 == null || irr.p95 == null || irr.p50 == null) {
      el.innerHTML = '<p class="chart-empty">No IRR distribution in this response.</p>';
      return;
    }
    const hRaw = document.getElementById("hurdle").value.trim();
    const hurdle = hRaw !== "" ? Number(hRaw) : null;
    const pts = [irr.p05, irr.p95, 0, irr.p50];
    if (hurdle != null && Number.isFinite(hurdle)) pts.push(hurdle);
    const { lo, hi } = bandDomain(pts);
    const left = pctInDomain(irr.p05, lo, hi);
    const right = pctInDomain(irr.p95, lo, hi);
    const width = Math.max(1.5, right - left);
    const med = pctInDomain(irr.p50, lo, hi);
    const z = pctInDomain(0, lo, hi);
    let refs =
      '<div class="h-band-ref h-band-ref--zero" style="left:' +
      z +
      '%"><span>0</span></div>';
    if (hurdle != null && Number.isFinite(hurdle)) {
      const hp = pctInDomain(hurdle, lo, hi);
      refs +=
        '<div class="h-band-ref h-band-ref--hurdle" style="left:' +
        hp +
        '%"><span>Hurdle ' +
        formatNum(hurdle, 3) +
        "</span></div>";
    }
    const downside =
      irr.p95 < 0
        ? "Simulated IRR stays <strong>negative</strong> up to the 95th percentile — weak upside in this setup."
        : irr.p05 < 0 && irr.p50 >= 0
          ? "Wide IRR span: left tail is <strong>negative</strong>, median is <strong>positive</strong>."
          : irr.p05 >= 0
            ? "Even the <strong>5th</strong> percentile IRR is non-negative in this draw."
            : "";
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
      (downside ? '<p class="h-band-legend">' + downside + "</p>" : "");
  }

  function renderBreachGauge(breach) {
    const el = document.getElementById("breachGauge");
    const p = Number(breach);
    if (!Number.isFinite(p)) {
      el.innerHTML = '<p class="chart-empty">—</p>';
      return;
    }
    const pct = Math.max(0, Math.min(100, p * 100));
    const label =
      pct < 15
        ? "Low — rarely breaks the loan rule in this toy world"
        : pct < 40
          ? "Moderate — worth reading the notes above"
          : "High — many simulated paths trip the loan";
    el.innerHTML =
      '<div class="gauge-row"><span class="gauge-val">' +
      pct.toFixed(1) +
      '%</span><span class="gauge-note">' +
      label +
      '</span></div><div class="gauge-track"><div class="gauge-fill" style="width:' +
      pct +
      '%"></div></div>';
  }

  function renderInsightCards(m, dscr, irr, covenantDscr) {
    const el = document.getElementById("insightCards");
    const cards = [];
    const cov = Number(covenantDscr);
    if (dscr.p05 != null && Number.isFinite(cov)) {
      const bad = dscr.p05 < cov;
      cards.push({
        cls: bad ? "insight-card--bad" : "insight-card--ok",
        title: "Bad luck vs the bank’s line",
        body: bad
          ? "In a rough simulated year, cash cover falls <strong>below</strong> what the bank requires (" +
            formatNum(cov, 2) +
            ") — that is where trouble usually starts."
          : "Even in a rough simulated year, cash cover stays <strong>at or above</strong> what the bank requires (" +
            formatNum(cov, 2) +
            ").",
      });
    }
    const breach = m.covenant_breach_probability;
    if (breach != null && Number.isFinite(breach)) {
      const high = breach > 0.35;
      cards.push({
        cls: high ? "insight-card--warn" : "insight-card--neutral",
        title: "How often the loan rule breaks",
        body:
          "In <strong>" +
          formatPct(breach) +
          "</strong> of the fake futures, cash drops below the bank’s rule. " +
          (high ? "That is a <strong>large</strong> share — treat as serious." : "Compare to how much risk you like to take."),
      });
    }
    if (dscr.std != null && Number.isFinite(dscr.std)) {
      const wide = dscr.std > 0.2;
      cards.push({
        cls: wide ? "insight-card--neutral" : "insight-card--ok",
        title: "How spread-out cash cover is",
        body: wide
          ? "Results swing a lot from run to run (spread score <strong>" +
            formatNum(dscr.std, 3) +
            "</strong>) — harder to pin down an outcome."
          : "Results cluster more tightly (spread score ≈ " + formatNum(dscr.std, 3) + ") — more predictable in this model.",
      });
    }
    if (irr && irr.p05 != null && irr.p50 != null) {
      const negTail = irr.p05 < 0;
      cards.push({
        cls: negTail ? "insight-card--warn" : "insight-card--ok",
        title: "Returns in a rough year",
        body: negTail
          ? "In a bad simulated year, yearly investor return can go <strong>negative</strong> (typical / middle case is about " +
            (100 * irr.p50).toFixed(1) +
            "% per year)."
          : "Even bad simulated years keep yearly return <strong>above zero</strong> (middle case about " +
            (100 * irr.p50).toFixed(1) +
            "% per year — still check your target hurdle).",
      });
    }
    el.innerHTML = cards
      .map(
        (c) =>
          '<article class="insight-card ' +
          c.cls +
          '"><h4 class="insight-card-title">' +
          c.title +
          '</h4><p class="insight-card-body">' +
          c.body +
          "</p></article>"
      )
      .join("");
  }

  function renderTrendCompare(prev, curr) {
    const panel = document.getElementById("trendPanel");
    const grid = document.getElementById("trendCompare");
    if (!prev || !curr) {
      panel.hidden = true;
      return;
    }
    const rows = [];
    if (curr.dscr.p50 != null && prev.dscrP50 != null) {
      const d = curr.dscr.p50 - prev.dscrP50;
      const good = d >= 0;
      rows.push({
        label: "Typical loan cover",
        val:
          '<span class="' +
          (good ? "trend-up" : "trend-down") +
          '">' +
          (good ? "▲" : "▼") +
          " " +
          formatDeltaNum(d) +
          "</span>",
        sub: formatNum(prev.dscrP50, 3) + " → " + formatNum(curr.dscr.p50, 3),
      });
    }
    if (curr.breach != null && prev.breach != null) {
      const d = curr.breach - prev.breach;
      const good = d <= 0;
      rows.push({
        label: "Loan rule breaks",
        val:
          '<span class="' +
          (good ? "trend-up" : "trend-down") +
          '">' +
          (d <= 0 ? "▼" : "▲") +
          " " +
          formatDeltaNum(100 * d, 1) +
          " pts</span>",
        sub: formatPct(prev.breach) + " → " + formatPct(curr.breach) + " of paths",
      });
    }
    if (curr.irr && curr.irr.p50 != null && prev.irrP50 != null) {
      const d = curr.irr.p50 - prev.irrP50;
      const good = d >= 0;
      rows.push({
        label: "Typical investor return",
        val:
          '<span class="' +
          (good ? "trend-up" : "trend-down") +
          '">' +
          (good ? "▲" : "▼") +
          " " +
          formatDeltaNum(d) +
          "</span>",
        sub: formatNum(prev.irrP50, 4) + " → " + formatNum(curr.irr.p50, 4),
      });
    }
    if (!rows.length) {
      panel.hidden = true;
      return;
    }
    panel.hidden = false;
    grid.innerHTML = rows
      .map(
        (r) =>
          '<div class="trend-item"><div class="trend-label">' +
          r.label +
          '</div><div class="trend-delta">' +
          r.val +
          '</div><div class="trend-sub">' +
          r.sub +
          "</div></div>"
      )
      .join("");
  }

  function formatDeltaNum(x, d = 4) {
    if (x == null || !Number.isFinite(x)) return "—";
    const sign = x > 0 ? "+" : "";
    return sign + Number(x).toFixed(d);
  }

  function renderCashFans(m) {
    const wrap = document.getElementById("cashPanel");
    const eEl = document.getElementById("ebitdaMini");
    const cEl = document.getElementById("leveredCfMini");
    const e = m.ebitda;
    const cf = m.levered_cf;
    let show = false;
    if (e && e.p05 != null) {
      show = true;
      eEl.innerHTML = miniFanHtml("EBITDA", e);
    } else {
      eEl.innerHTML = "";
    }
    if (cf && cf.p05 != null) {
      show = true;
      cEl.innerHTML = miniFanHtml("Levered CF", cf, true);
    } else {
      cEl.innerHTML = "";
    }
    wrap.hidden = !show;
  }

  function miniFanHtml(title, s, currencyShort) {
    const fmt = (v) =>
      currencyShort && Math.abs(v) >= 1e6
        ? (v / 1e6).toFixed(2) + "M"
        : formatNum(v, 0);
    const lo = Math.min(s.p05, s.p95);
    const hi = Math.max(s.p05, s.p95);
    const span = hi - lo || 1;
    const l = ((s.p05 - lo) / span) * 100;
    const w = Math.max(8, ((s.p95 - s.p05) / span) * 100);
    const m = ((s.p50 - lo) / span) * 100;
    return (
      '<div class="mini-fan-inner"><h5 class="mini-fan-title">' +
      title +
      '</h5><div class="mini-fan-track"><div class="mini-fan-band" style="left:' +
      l +
      "%;width:" +
      w +
      '%"></div><div class="mini-fan-tick" style="left:' +
      m +
      '%"></div></div><div class="mini-fan-labels"><span>Low ' +
      fmt(s.p05) +
      "</span><span>Mid " +
      fmt(s.p50) +
      "</span><span>High " +
      fmt(s.p95) +
      "</span></div></div>"
    );
  }

  function renderResults(data, options) {
    const skipSnapshot = options && options.skipSnapshot;
    const wrap = document.getElementById("resultsWrap");
    wrap.hidden = false;
    const tb = document.querySelector("#tblSummary tbody");
    tb.innerHTML = "";
    const m = data.metrics || {};
    const dscr = m.dscr || {};
    const irr = m.irr_annual || {};
    const covenant = lastRunContext.covenantDscr;

    const prevSnap = previousSnapshot;

    renderPlainLanguageBlock(m, dscr, irr, covenant);

    row(tb, "Covenant DSCR (from inputs)", formatNum(covenant, 2));
    row(tb, "Run id", data.metadata?.run_id || "—");
    row(tb, "Scenarios", data.metadata?.n_scenarios ?? "—");
    row(tb, "Compute (ms)", data.metadata?.compute_time_ms ?? "—");
    row(
      tb,
      "P(DSCR &lt; covenant)",
      formatPct(m.covenant_breach_probability)
    );
    row(tb, "P(DSCR &lt; 1.0) proxy", formatPct(m.probability_of_default_proxy_dscr_lt_1));
    row(tb, "DSCR p05 (tail)", formatNum(dscr.p05, 4));
    row(tb, "DSCR p50", formatNum(dscr.p50, 4));
    row(tb, "DSCR p90", formatNum(dscr.p90, 4));
    row(tb, "DSCR p95", formatNum(dscr.p95, 4));
    row(tb, "IRR p50 (annual)", formatNum(irr.p50, 4));
    row(tb, "IRR p05 (annual)", formatNum(irr.p05, 4));
    row(tb, "VaR IRR (95%, vs median)", formatNum(m.var_irr_95, 4));
    row(tb, "CVaR IRR (95% tail mean)", formatNum(m.cvar_irr_95, 4));
    row(tb, "Merton-style equity PD proxy", formatPct(m.merton_equity_pd_proxy));

    renderBars("dscrBars", dscr);
    renderBars("irrBars", irr);

    renderRiskProbChart(m);
    renderNamedBars("irrTailBars", [
      ["Rough patch", irr?.p05],
      ["Worst 5% average", m.cvar_irr_95],
      ["Typical (middle)", irr?.p50],
      ["Strong upside", irr?.p95],
    ]);
    renderCashDistributionBars(m);
    renderNavProxyBand(m.nav_proxy_equity);

    renderInsightCards(m, dscr, irr, covenant);
    renderTrendCompare(prevSnap, {
      dscr,
      irr,
      breach: m.covenant_breach_probability,
    });
    renderDscrCovenantBand(dscr, covenant);
    renderIrrBandChart(irr);
    renderBreachGauge(m.covenant_breach_probability);
    renderCashFans(m);

    document.getElementById("rawOut").textContent = JSON.stringify(data, null, 2);

    const hurdleEl = document.getElementById("hurdle");
    const hMsg = document.getElementById("hurdleMsg");
    const hRaw = hurdleEl.value.trim();
    hMsg.textContent = "";
    if (hRaw !== "" && irr && irr.p05 != null) {
      const h = Number(hRaw);
      if (!Number.isNaN(h)) {
        hMsg.textContent =
          irr.p05 < h
            ? `Plain English: in a bad simulated year, yearly return is about ${(100 * irr.p05).toFixed(1)}%, below your ${(100 * h).toFixed(1)}% target. Technical: IRR p05 ${formatNum(irr.p05, 4)} vs hurdle ${formatNum(h, 4)}.`
            : `Plain English: even in a rough simulated year (${(100 * irr.p05).toFixed(1)}%/yr), you still meet or beat the ${(100 * h).toFixed(1)}% target. Technical: IRR p05 ${formatNum(irr.p05, 4)} vs hurdle ${formatNum(h, 4)}.`;
      }
    }

    if (!skipSnapshot) {
      previousSnapshot = {
        dscrP50: dscr.p50,
        breach: m.covenant_breach_probability,
        irrP50: irr?.p50,
      };
    }
  }

  async function runSimulation() {
    const status = document.getElementById("status");
    status.textContent = "";
    status.classList.remove("err");

    const n = document.getElementById("nScenarios").value;
    const seed = document.getElementById("seed").value;
    const yahoo = document.getElementById("yahooCopper").checked;
    const yahooSymbol = document.getElementById("yahooSymbol").value;
    const yahooPeriod = document.getElementById("yahooPeriod").value;
    const shocks = parseShockInputs();

    let asset;
    try {
      asset = assetFromForm();
    } catch (e) {
      status.textContent = "Invalid asset JSON: " + e.message;
      status.classList.add("err");
      return;
    }

    asset = buildAssetWithShocks(asset, shocks);
    const shockpack = baseShockpack(n, seed, yahoo, yahooSymbol, yahooPeriod);

    const headers = { "Content-Type": "application/json" };
    if (API_KEY) {
      headers["X-API-Key"] = API_KEY;
    }

    status.textContent = "Running…";
    const nNum = Number(n);
    const performance_profile =
      nNum > 5000 ? "standard" : "interactive";
    try {
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
        const msg =
          typeof detail === "string" ? detail : JSON.stringify(detail);
        if (res.status === 401) {
          throw new Error(
            "Unauthorized (401). Check that API_KEY in frontend/app.js matches AZRAQ_API_KEY in the server .env and that you opened this page from the same host as the API (e.g. /app/)."
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
      renderResults(data);
      status.textContent = "Done.";
    } catch (e) {
      status.textContent = "Error: " + e.message;
      status.classList.add("err");
    }
  }

  bindRangeNumber("capexPctRange", "capexPct", null);
  bindRangeNumber("opexPctRange", "opexPct", null);
  bindRangeNumber("rateBpsRange", "rateBps", 25);

  function syncYahooPanel() {
    const on = document.getElementById("yahooCopper").checked;
    const panel = document.getElementById("yahooPanel");
    panel.classList.toggle("yahoo-panel--disabled", !on);
    document.getElementById("yahooSymbol").disabled = !on;
    document.getElementById("yahooPeriod").disabled = !on;
    updateShockSummary();
  }

  document.getElementById("yahooCopper").addEventListener("change", syncYahooPanel);
  document.getElementById("yahooSymbol").addEventListener("input", updateShockSummary);
  document.getElementById("yahooPeriod").addEventListener("change", updateShockSummary);

  document.getElementById("runBtn").addEventListener("click", runSimulation);
  document
    .getElementById("resetAsset")
    .addEventListener("click", () => {
      document.getElementById("assetJson").value = JSON.stringify(DEFAULT_ASSET, null, 2);
    });
  document.getElementById("hurdle").addEventListener("input", () => {
    const raw = document.getElementById("rawOut").textContent;
    if (!raw) return;
    try {
      renderResults(JSON.parse(raw), { skipSnapshot: true });
    } catch {
      /* ignore */
    }
  });

  document.getElementById("assetJson").value = JSON.stringify(DEFAULT_ASSET, null, 2);
  syncYahooPanel();
  updateShockSummary();
})();
