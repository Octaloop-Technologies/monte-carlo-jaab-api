# Monte Carlo Scenario Lab — plain-language guide

This page is for **non-technical** readers using the **“Monte Carlo scenario lab”** screen (the investor dashboard). It explains **what order to work in**, **how “real data” fits in**, and **what the numbers mean** — without JSON or programming jargon.

Technical detail for the same engine lives in **[MONTE_CARLO_FLOW_AND_VALIDATION.md](MONTE_CARLO_FLOW_AND_VALIDATION.md)** and **[INTEGRATION.md](INTEGRATION.md)**.

---

## Big picture (one sentence)

You describe **one project** (money in, money out, loan rules), then you describe **how uncertain the world is** (volatilities and optional market-based calibration), then you optionally add a **specific stress story** (higher costs or rates). The lab runs **thousands of possible futures** and shows **ranges** and **risk of breaking the bank’s rules** — not a single guess.

---

## How the three sections connect (simple picture)

Mermaid diagrams are easy to break in viewers; use this **ASCII** version instead.

**At a glance**

| You fill in… | It answers the question… |
|--------------|----------------------------|
| **Section 1** | “What is the project *today*?” |
| **Section 2** | “How *random* is the world?” (+ optional Yahoo for copper volatility) |
| **Section 3** | “Do we also assume a *fixed* bad start (higher costs / rate) before randomness?” |

**Picture (read top → bottom, then left + right into “Run”)**

```
  SECTION 1                SECTION 3
  (your project)           (optional stress: presets / sliders)
       \                         /
        \                       /
         --------+-------------+---------->  ONE project picture for this run
                   \                        (section 3 tilts the same deal)
                    \
                     \
  SECTION 2 -------------------------------->  HOW randomness works
  (how many runs, seed, volatilities)              |
        |                                          |
        +---- Yahoo ON?  ----------------> server sets build-cost volatility from market history
        +---- Yahoo OFF? ----------------> use the copper / build volatility you typed

                              |
                              v
                    [ Run: many futures ]
                              |
                              v
                    Charts + breach %
```

**How to read it**

- **Two streams merge:** **Project** (sections **1 + 3**) meets **Risk** (section **2**) when you press **Run**. The engine always needs **both**.
- **Yahoo is only a branch inside section 2:** it changes **how** build/capex randomness is calibrated — not your revenue line in section 1.
- **Section 3 is not “instead of” section 2:** sliders add a **fixed** tilt; section 2 still sets **how wide** the random paths are.

**Important nuance:** Section **3** does **not** replace the randomness in section **2**. Section 3 applies a **fixed tilt** (e.g. “costs are 10% higher than my base case before we even roll the dice”). Section 2 still controls **how wildly** revenue, costs, and rates **move around** in the simulation.

---

## Step-by-step: what to do in order

### Step 1 — Enter your project (section 1)

Fill in the **facts of the deal** as you know them today:

- **Money:** revenue, operating cost, capital cost, how much is debt vs equity.
- **Loan:** interest rate, length of loan, **minimum DSCR** the bank cares about (covenant).
- **Labels:** case name and time horizon so you recognise this run later.

**Tip:** Think of this as “the spreadsheet row for our base project.” If these numbers are wrong, everything downstream is wrong — so get finance to agree on them first.

---

### Step 2 — Set how uncertain the world is (section 2)

Here you are **not** picking one future; you are saying **how noisy** each driver is:

- **Number of simulations:** more futures → smoother charts (often 2,500 is a good balance).
- **Random seed:** a technical “replay button” — same seed + same inputs → same random draws (useful when comparing two setups fairly).
- **Volatility fields (interest, electricity, FX, CPI, copper):** higher numbers mean **wider swings** in the model for that factor. The lab maps electricity + CPI together into **one combined operating-cost volatility** for the engine.

**Using real market data (Yahoo Finance)**

1. Tick **calibrate copper / build-cost volatility from Yahoo** (wording may vary slightly in the UI).
2. The default symbol is typically **copper futures** (`HG=F`). You can change symbol or history length if the panel allows it.
3. When you run, the **server** looks at **past prices**, estimates how volatile they were, and uses that to set **how much random variation** applies to **build / capex-related risk** in the Monte Carlo — **unless** you leave the box unticked, in which case your **typed** copper/build volatility is used instead.

**What real data does *not* do:** it does **not** import your private invoices or live feeds every second. It **calibrates one volatility knob** from public price history so the randomness is grounded in recent markets.

---

### Step 3 — Choose a story to stress-test (section 3)

Pick a **preset** (base case, rate shock, cost shock, combined) or move the **sliders**:

- **Extra on build / “copper weight”:** raises the **baseline** build cost by that percentage **before** randomness is applied (materials stress story).
- **Extra OPEX %:** raises baseline operating cost the same way.
- **Extra coupon (basis points):** raises the **starting** interest rate for the loan by that many bps (e.g. +200 bps = +2 percentage points on the rate), capped by safety limits in the tool.

Then click **Run this scenario** to see distributions and breach risk for **that** combined story.

---

### Optional — Compare copper ladder

**Compare copper ladder** runs the same model **four times** with **0%, +5%, +10%, +15%** extra build-cost stress (and shows a small comparison table). Use it when you want a **quick side-by-side** of “how bad does risk get if materials run hotter?” without changing sliders manually each time.

---

## How to read the results (non-technical)

After a run, look for:

- **Debt service coverage (DSCR):** a band showing “typical range” vs the **red covenant line**. If a lot of the range sits **below** the line, the project is fragile under your assumptions.
- **Chance of covenant breach:** plain probability that the modelled DSCR drops below the bank floor in the simulated futures.
- **IRR:** range of investor returns; compare to your **hurdle** rate if the screen shows that.

Use **`response_help`** inside API JSON only if a technical colleague shares it — it repeats the same ideas in plain language.

---

## Quick reference: two kinds of “shock” in this lab

| You touch… | Meaning |
|------------|---------|
| **Volatility numbers + Yahoo checkbox (section 2)** | “How much randomness?” — **many** futures, each different. |
| **Presets / sliders (section 3)** | “Assume this bad tilt on top of my base case” — **one** fixed adjustment, then still many random futures. |

---

## If something looks wrong

1. Re-check **section 1** against your internal model.
2. Run **Base case** in section 3 (no extra stress) with **moderate** volatilities — note breach probability and DSCR band.
3. Turn **on** Yahoo calibration and run again — **only** the random **build-cost volatility** side should change materially (not your typed revenue unless you change other fields).
4. Ask IT whether the page is opened from the **same host** as the API and whether an **API key** is required — otherwise the run button may error.

---

## Where this sits in the product

The lab is a **friendly front end** for the same risk engine as **`POST /v1/simulate/asset`**. The **Advanced — JSON** panel is a read-only mirror for developers; you can ignore it for day-to-day use.
