"""Plain-English `response_help` in each API response for non-technical readers."""
from __future__ import annotations

from typing import Any


def help_block(
    *,
    what_you_sent: str,
    what_you_received: str,
    findings_and_next_steps: str,
    glossary: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Standard shape: request → response → what it means / what to do next."""
    out: dict[str, Any] = {
        "what_you_sent": what_you_sent,
        "what_you_received": what_you_received,
        "findings_and_next_steps": findings_and_next_steps,
    }
    if glossary:
        out["glossary"] = glossary
    return out


# --- Monte Carlo and related result types (schemas computed_field) ---

SIMULATION_RESULT = help_block(
    what_you_sent=(
        "You sent one project’s finances (revenue, costs, debt, etc.) plus how many random "
        "‘what-if’ worlds to run and how strongly costs and rates can move together."
    ),
    what_you_received=(
        "You get a summary of thousands of possible futures: typical and stressed debt cover (DSCR), "
        "chance of breaking loan rules, and (if requested) which kinds of shocks showed up most in bad outcomes."
    ),
    findings_and_next_steps=(
        "Start with the chance of covenant breach and the low/middle/high debt-cover numbers. "
        "If something looks too risky, change assumptions or talk to your modeller before deciding. "
        "Optional ‘attribution’ is a story aid only—not a bank approval."
    ),
    glossary={
        "metadata": "Labels for this run: IDs, how many worlds were run, random seed, timing.",
        "metrics": "The risk numbers: debt cover bands, breach rate, cash flow summaries.",
        "attribution": "Which drivers tend to appear when outcomes are worst (if you asked for it).",
        "full_stack": "Extra delivery and operations-style results when you use the expanded 12-risk setup.",
        "extensions": "Optional extra notes (e.g. interest-rate ladder summary, reserve-style charges, cache hints).",
    },
)

BASE_CASE_RESULT = help_block(
    what_you_sent="You sent one project’s finances only—no random stress test.",
    what_you_received=(
        "You get a single set of figures: one debt-cover ratio, one return figure, "
        "and steady revenue/EBITDA style outputs—as if nothing random happened."
    ),
    findings_and_next_steps=(
        "Use this to check that the model matches a spreadsheet baseline. "
        "It does **not** show how bad things could get in rare events—for that, run a full simulation."
    ),
    glossary={
        "metadata": "Run labels; this run uses exactly one synthetic world, not many.",
        "base": "The headline numbers: debt cover, return, cash available versus debt payments, equity in.",
    },
)

PORTFOLIO_SIMULATION_RESULT = help_block(
    what_you_sent=(
        "You sent two or more projects plus one shared random setup so **the same bad year can hit several sites at once**."
    ),
    what_you_received=(
        "You get risk results **per project** and **for the whole book**: chance **any** site breaks a covenant, "
        "weakest debt cover across sites, and how concentrated revenue is."
    ),
    findings_and_next_steps=(
        "The ‘any breach’ probability is **not** the sum of each site’s probability—shared bad luck matters. "
        "Look at the weakest debt cover across assets to see the weakest link."
    ),
    glossary={
        "metadata": "Portfolio name, list of assets, how many worlds were run.",
        "per_asset": "Each site’s risk numbers, same style as a single-asset run.",
        "portfolio": "Whole-book numbers: joint breach risk, weakest link, totals.",
    },
)

CALIBRATION_PREVIEW = help_block(
    what_you_sent=(
        "You sent your risk setup and, optionally, asked the system to **fill in uncertainty sizes** from a "
        "saved file, a trusted web JSON, or **public market history** (for example Yahoo Finance)."
    ),
    what_you_received=(
        "You get the **same kind of setup back**, with those uncertainty sizes **filled in**. "
        "**No** large random simulation was run—this step only prepares the numbers."
    ),
    findings_and_next_steps=(
        "When the numbers look right, copy this updated setup into a **full simulation** request. "
        "If you see an audit diary (calibration trace), use it to confirm which source was used and what changed."
    ),
    glossary={
        "resolved_shockpack": (
            "Your risk setup with uncertainty figures filled in—ready to plug into a simulation call."
        ),
        "calibration_trace": (
            "Empty if nothing was auto-filled, otherwise a short log of each source used and what it changed."
        ),
    },
)

SCHEDULED_ASSET_RESPONSE = help_block(
    what_you_sent="Same as a normal single-project simulation, with options to save a copy of the result on the server.",
    what_you_received=(
        "The full simulation result plus, when saving is on, the **file path** where a copy was stored."
    ),
    findings_and_next_steps=(
        "If you have a file path, you can compare this run to an older saved run later to see **what changed** "
        "in risk and in inputs."
    ),
    glossary={
        "result": "The full risk outcome object (with its own plain-English help inside).",
        "snapshot_path": "Where the server saved a JSON copy, or empty if you turned saving off.",
    },
)

# --- Small dict responses (merged in api.py) ---

HEALTH = help_block(
    what_you_sent="Nothing—this is a quick ping.",
    what_you_received='A short JSON saying the service answered (for example status "ok").',
    findings_and_next_steps=(
        "If this fails, the app is not reachable—fix hosting before trying heavier calls. "
        "This ping does **not** prove a database or simulation works."
    ),
)

MARKET_HISTORY = help_block(
    what_you_sent="A market symbol (like a commodity or index code) and how far back to look.",
    what_you_received=(
        "A table of **dates and prices** from public market data (via Yahoo Finance in the backend)."
    ),
    findings_and_next_steps=(
        "Use this to **eyeball** that the symbol and history look sensible. "
        "Feeding this into the model’s uncertainty step uses a slightly different maths path—ask your technical contact if you need detail."
    ),
    glossary={
        "symbol": "The market code you asked for.",
        "period": "How much history (for example one year).",
        "data": "Rows of prices over time.",
    },
)

ECB_EUR_USD = help_block(
    what_you_sent="Nothing—the server requests the European Central Bank’s public daily exchange-rate file.",
    what_you_received=(
        "The **date** stamped on that file and how many US dollars equal **one euro** on that date "
        "(ECB convention: `one_eur_in_usd`)."
    ),
    findings_and_next_steps=(
        "Use for FX checks or to copy into your own margin file / JSON bridge. "
        "It does **not** change simulation parameters until you wire it into `dynamic_margins` or a saved shock pack."
    ),
    glossary={
        "rate_date": "Business date the ECB assigned to this set of rates.",
        "one_eur_in_usd": "How many USD one EUR buys per ECB daily publication.",
    },
)

MARKET_RETURNS = help_block(
    what_you_sent="A market symbol and a history length.",
    what_you_received="Day-to-day **percentage changes** in closing price—easier to judge ups and downs than raw levels.",
    findings_and_next_steps=(
        "Good for a quick sense of volatility. The model’s auto-fill step may use related but not identical steps internally."
    ),
    glossary={"returns": "Each day’s change versus the previous close.", "n": "How many return rows you got."},
)

FULL_STACK_CATALOG = help_block(
    what_you_sent="Nothing beyond normal access—this just lists the expanded risk list.",
    what_you_received=(
        "The **ordered names** of extra risks (delivery delays, power, cyber, etc.) and short blurbs for each."
    ),
    findings_and_next_steps=(
        "Use this list to line up a larger correlation table before running the expanded ‘full stack’ mode with your technical lead."
    ),
)

CATALOG_REGISTER = help_block(
    what_you_sent="A full risk-setup package you want stored for reuse.",
    what_you_received="A new **ID code** you can put on future simulation calls instead of pasting the whole package.",
    findings_and_next_steps=(
        "Store the ID safely. You can still send small overrides (like a different random seed) together with that ID if needed."
    ),
)

CATALOG_PROMOTE = help_block(
    what_you_sent="An existing stored package ID and the **environment stage** you want (for example production).",
    what_you_received="Confirmation the stage label was updated.",
    findings_and_next_steps=(
        "Downstream tools can list only ‘production’ packages so people don’t accidentally run draft setups."
    ),
)

CATALOG_ENTRY = help_block(
    what_you_sent="The ID of one stored package.",
    what_you_received="Everything stored with it: version, tenant labels, fingerprints, and the **full setup JSON**.",
    findings_and_next_steps=(
        "Review the setup JSON before large or regulated runs. Mismatch with what you expect means stop and verify."
    ),
    glossary={
        "spec": "The saved risk-setup object—the same shape you would send inline to a simulation.",
    },
)

CATALOG_LIST = help_block(
    what_you_sent="Optional filters (how many rows, which tenant, which stage).",
    what_you_received="A **short list** of stored packages (IDs and labels—not the full setup each time).",
    findings_and_next_steps=(
        "Pick an ID here, then call ‘get one’ if you need the full setup body."
    ),
    glossary={"entries": "Rows summarising each stored package."},
)

SHOCK_EXPORT_NPZ = help_block(
    what_you_sent="A risk-setup package; the server will draw random numbers and save them to disk.",
    what_you_received="The **path to a file** of raw random draws (technical NumPy format).",
    findings_and_next_steps=(
        "This file is **not** debt cover or profit—only random inputs. Specialists use it in other tools; "
        "business readers should use normal simulation responses instead."
    ),
)

SNAPSHOT_SAVE = help_block(
    what_you_sent="A full prior result JSON you asked the server to keep on disk.",
    what_you_received="The **path** to the saved file.",
    findings_and_next_steps="Use that path in list or compare runs later for audit trails.",
)

SNAPSHOT_LIST = help_block(
    what_you_sent="Nothing—asks what saved result files exist.",
    what_you_received="A list of **file paths** on the server.",
    findings_and_next_steps="Choose two paths to compare how risk or inputs changed over time.",
)

AUDIT_RUNS = help_block(
    what_you_sent="How many recent log rows you want.",
    what_you_received="A list of **who ran what** recently (if logging is turned on).",
    findings_and_next_steps=(
        "Match a **run id** here to the run id inside a saved result for compliance checks."
    ),
)

STRESS_DATA_CATALOG = help_block(
    what_you_sent="Nothing—this is a reference list (Appendix J style) for analysts and engineers.",
    what_you_received=(
        "A table of stress drivers (commodities, power, FX, rates, etc.) with official or example URLs, "
        "how they connect to this engine, and which integration path applies (Yahoo, ECB endpoint, HTTP JSON, file, manual)."
    ),
    findings_and_next_steps=(
        "Pick a row, then use the matching path: Yahoo tickers for quick vol calibration, "
        "GET /v1/market/ecb/eur-usd for ECB spot, or host IEA/NY Fed/BoE data as JSON for dynamic_margins.http. "
        "The simulator still runs without these feeds—only the **parameters** change."
    ),
    glossary={
        "sources": "Each Appendix J row with urls, tiers, and mapping hints.",
        "integration_overview": "Short guide to yahoo vs ecb vs http vs file vs manual.",
    },
)

SNAPSHOT_DIFF = help_block(
    what_you_sent="Two saved result file paths: an older and a newer run of the same style.",
    what_you_received=(
        "**Numbers:** how key risk metrics moved. **Story:** what inputs or settings changed between the two."
    ),
    findings_and_next_steps=(
        "Read **what changed in inputs** first (loan terms, shock setup, random seed, etc.), "
        "then look at **how risk numbers moved**. That order avoids mistaking a model tweak for real-world risk."
    ),
    glossary={
        "metrics_delta": "Before / after / gap for important risk outputs.",
        "provenance_delta": "Flags showing whether assumptions, shock package, seed, catalogue link, or speed profile changed.",
    },
)
