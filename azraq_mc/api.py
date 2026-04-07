from __future__ import annotations

import asyncio
import os
from pathlib import Path

from typing import Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, WebSocket
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from azraq_mc.api_audit import audit_simulation
from azraq_mc.api_deps import optional_api_key, read_tenant_id, read_user_id, require_catalog_promoter
from azraq_mc.api_schemas import (
    AdhocSimulationRequest,
    CalibrationPreviewResponse,
    PortfolioSimulationRequest,
    ScheduledAssetRequest,
    ScheduledAssetResponse,
    ShockExportRequest,
    SnapshotSaveRequest,
)
from azraq_mc.audit import fetch_recent_runs
from azraq_mc.calibration_sources import materialize_shockpack_margins
from azraq_mc.engine import run_adhoc_asset_simulation
from azraq_mc.presets import FULL_STACK_FACTOR_ORDER, FULL_STACK_RISK_FACTOR_CATALOG
from azraq_mc.io_shockpack import save_shockpack_npz
from azraq_mc.market_data import ecb_eur_usd_daily, yfinance_close_returns, yfinance_history
from azraq_mc.monitoring import run_scheduled_asset_simulation
from azraq_mc.portfolio import run_portfolio_joint_simulation
from azraq_mc.request_resolve import resolve_shockpack_for_request
from azraq_mc.response_help import (
    AUDIT_RUNS,
    CATALOG_ENTRY,
    CATALOG_LIST,
    CATALOG_PROMOTE,
    CATALOG_REGISTER,
    FULL_STACK_CATALOG,
    HEALTH,
    MARKET_HISTORY,
    MARKET_RETURNS,
    SHOCK_EXPORT_NPZ,
    SNAPSHOT_LIST,
    SNAPSHOT_SAVE,
    STRESS_DATA_CATALOG,
    ECB_EUR_USD,
)
from azraq_mc.stress_data_catalog import catalog_integration_overview, stress_data_catalog
from azraq_mc.schemas import AssetAssumptions, BaseCaseResult, PortfolioSimulationResult, ShockPackSpec, SimulationResult
from azraq_mc.shockpack_catalog import list_entries, load_entry, promote_entry, register_spec
from azraq_mc.shockpack import build_shock_array
from azraq_mc.snapshots import diff_simulation_results, list_snapshots, load_snapshot_typed, save_snapshot
from azraq_mc.v0 import run_v0_base_case

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

app = FastAPI(
    title="Azraq Monte Carlo Risk Engine",
    version="1.0",
    description=(
        "Risk engine: Monte Carlo shocks → DSCR / IRR / covenant metrics. "
        "In **/docs**, expand any operation: summary + description explain **what to send** and **what you get**. "
        "Full **Description / You send / You get / Analysis** for each route: see **docs/API.md → Endpoints**."
    ),
)


def _ep(
    *,
    desc: str,
    send: str,
    get: str,
    analysis: str,
) -> str:
    """Standard API docs block for OpenAPI (v3 description is plain text / commonmark in Swagger UI)."""
    return (
        f"**Description:** {desc}\n\n"
        f"**You send:** {send}\n\n"
        f"**You get:** {get}\n\n"
        f"**Analysis:** {analysis}"
    )


def _snapshot_root() -> Path:
    return Path(os.environ.get("AZRAQ_SNAPSHOT_DIR", "data/snapshots"))


def _shock_export_root(req_dir: str | None) -> Path:
    if req_dir:
        return Path(req_dir)
    return Path(os.environ.get("AZRAQ_SHOCK_EXPORT_DIR", "data/shockpacks"))


@app.get(
    "/health",
    summary="Liveness check",
    description=_ep(
        desc="Public probe: is the HTTP server responding?",
        send="Nothing (no API key).",
        get='JSON `{"status":"ok"}` on success.',
        analysis="Use for monitoring or before other calls. Does not run the financial model.",
    ),
)
def health() -> dict[str, object]:
    return {"status": "ok", "response_help": dict(HEALTH)}


@app.get(
    "/v1/market/yfinance/{symbol}/history",
    dependencies=[Depends(optional_api_key)],
    summary="Yahoo Finance OHLCV history",
    description=_ep(
        desc="Download price history for a symbol (e.g. HG=F copper) for inspection or reporting.",
        send="Path `symbol`; query `period` (default 1y). Optional X-API-Key if AZRAQ_API_KEY is set.",
        get='`symbol`, `period`, `data` rows. 404 if no series; 501 if yfinance missing.',
        analysis="Exploratory market data only. To feed volatility into shocks use dynamic_margins.yahoo_finance or POST /v1/calibration/preview.",
    ),
)
def market_yfinance_history(symbol: str, period: str = "1y") -> dict[str, object]:
    try:
        out = yfinance_history(symbol, period=period)
        out["response_help"] = dict(MARKET_HISTORY)
        return out
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ImportError as e:
        raise HTTPException(status_code=501, detail=str(e))


@app.get(
    "/v1/market/yfinance/{symbol}/returns",
    dependencies=[Depends(optional_api_key)],
    summary="Yahoo Finance close returns",
    description=_ep(
        desc="Simple returns on closes — closer to intuition for volatility than raw OHLCV.",
        send="Path `symbol`; query `period`. Optional API key.",
        get="`returns` time series + `n`. 404 / 501 as for history.",
        analysis="Internal calibration uses log returns + annualisation; this endpoint is for human review.",
    ),
)
def market_yfinance_returns(symbol: str, period: str = "1y") -> dict[str, object]:
    try:
        out = yfinance_close_returns(symbol, period=period)
        out["response_help"] = dict(MARKET_RETURNS)
        return out
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ImportError as e:
        raise HTTPException(status_code=501, detail=str(e))


@app.get(
    "/v1/market/ecb/eur-usd",
    dependencies=[Depends(optional_api_key)],
    summary="ECB daily EUR/USD reference rate",
    description=_ep(
        desc="Official USD rate against EUR from ECB daily euro foreign exchange reference XML.",
        send="Nothing; optional API key if configured.",
        get="rate_date, one_eur_in_usd, source_url + response_help.",
        analysis="Complements Yahoo for FX; use http_json/file to inject derived margin patches into simulate.",
    ),
)
def market_ecb_eur_usd() -> dict[str, object]:
    try:
        out = ecb_eur_usd_daily()
        out["response_help"] = dict(ECB_EUR_USD)
        return out
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get(
    "/v1/calibration/stress-data-catalog",
    dependencies=[Depends(optional_api_key)],
    summary="Appendix J — stress / calibration source catalogue",
    description=_ep(
        desc="Reference list of macro inputs (commodities, power, FX, rates) with URLs and engine mapping hints.",
        send="Nothing beyond optional API key.",
        get="sources[], integration_overview{}, response_help.",
        analysis="Use with dynamic_margins (Yahoo/http/file) — engine does not require live feeds to run.",
    ),
)
def calibration_stress_data_catalog() -> dict[str, object]:
    return {
        "sources": stress_data_catalog(),
        "integration_overview": catalog_integration_overview(),
        "response_help": dict(STRESS_DATA_CATALOG),
    }


@app.get(
    "/v1/catalog/full-stack-factors",
    dependencies=[Depends(optional_api_key)],
    summary="Full-stack factor catalog",
    description=_ep(
        desc="Lists factor_order and metadata for 12-factor full-stack mode.",
        send="Nothing beyond optional API key.",
        get="`factor_order` array and `risk_factors` catalog entries.",
        analysis="Use before building a 12× correlation matrix or enabling asset.full_stack.",
    ),
)
def catalog_full_stack_factors() -> dict[str, object]:
    return {
        "factor_order": list(FULL_STACK_FACTOR_ORDER),
        "risk_factors": [rf.model_dump(mode="json") for rf in FULL_STACK_RISK_FACTOR_CATALOG],
        "response_help": dict(FULL_STACK_CATALOG),
    }


@app.post(
    "/v1/calibration/preview",
    response_model=CalibrationPreviewResponse,
    dependencies=[Depends(optional_api_key)],
    summary="Resolve dynamic_margins without simulation",
    description=_ep(
        desc="Apply file/http/Yahoo calibration to margins; no scenario draw.",
        send="Full ShockPackSpec JSON body (often with dynamic_margins).",
        get="resolved_shockpack + calibration_trace; safe to paste into simulate routes.",
        analysis="Governance: verify resolved margins before an expensive Monte Carlo run.",
    ),
)
def calibration_preview(shockpack: ShockPackSpec) -> CalibrationPreviewResponse:
    resolved, trace = materialize_shockpack_margins(shockpack)
    return CalibrationPreviewResponse(resolved_shockpack=resolved, calibration_trace=trace)


@app.post(
    "/v1/simulate/scheduled/asset",
    response_model=ScheduledAssetResponse,
    dependencies=[Depends(optional_api_key)],
    summary="Simulate asset + optional snapshot file",
    description=_ep(
        desc="Same as /v1/simulate/asset for metrics; can persist JSON snapshot for drift/diff.",
        send="ScheduledAssetRequest (asset + shockpack or catalogue id + label/persist/model_version).",
        get="result (SimulationResult) + snapshot_path or null.",
        analysis="Pairs with snapshots/diff for Mode 2 monitoring of metric + provenance drift.",
    ),
)
def simulate_scheduled_asset(
    req: ScheduledAssetRequest,
    user: str | None = Depends(read_user_id),
) -> ScheduledAssetResponse:
    sp, cid = resolve_shockpack_for_request(req.shockpack, req.shockpack_catalog_entry_id)
    result, path = run_scheduled_asset_simulation(
        sp,
        req.asset,
        snapshot_root=_snapshot_root(),
        label=req.label,
        persist=req.persist,
        model_version=req.model_version,
        include_attribution=req.include_attribution,
        include_advanced_attribution=req.include_advanced_attribution,
        user_id=user,
        performance_profile=req.performance_profile,
        shockpack_catalog_entry_id=cid,
    )
    audit_simulation("scheduled_monitoring", result, user_id=user, client_hint="http:scheduled")
    return ScheduledAssetResponse(
        result=result,
        snapshot_path=str(path.resolve()) if path is not None else None,
    )


@app.post(
    "/v1/simulate/asset",
    response_model=SimulationResult,
    dependencies=[Depends(optional_api_key)],
    summary="Monte Carlo — single asset",
    description=_ep(
        desc="Main risk run: many correlated shock paths → DSCR/IRR/breach metrics for one project.",
        send="AdhocSimulationRequest: required asset; shockpack and/or shockpack_catalog_entry_id; optional attribution flags.",
        get="SimulationResult: metadata, metrics, optional attribution/full_stack/extensions.",
        analysis="Read covenant_breach_probability and DSCR percentiles for tail risk; attribution is indicative.",
    ),
)
def simulate_asset(
    req: AdhocSimulationRequest,
    user: str | None = Depends(read_user_id),
) -> SimulationResult:
    sp, cid = resolve_shockpack_for_request(req.shockpack, req.shockpack_catalog_entry_id)
    result = run_adhoc_asset_simulation(
        sp,
        req.asset,
        include_attribution=req.include_attribution,
        include_advanced_attribution=req.include_advanced_attribution,
        attribution_tail_fraction=req.attribution_tail_fraction,
        user_id=user,
        performance_profile=req.performance_profile,
        shockpack_catalog_entry_id=cid,
    )
    audit_simulation("adhoc_asset", result, user_id=user, client_hint="http:asset")
    return result


@app.post(
    "/v1/simulate/v0/base-case",
    response_model=BaseCaseResult,
    dependencies=[Depends(optional_api_key)],
    summary="Deterministic base case (no MC)",
    description=_ep(
        desc="Single zero-shock path — fast tie-out vs spreadsheet baseline.",
        send="AssetAssumptions as raw JSON body (not wrapped).",
        get="BaseCaseResult with metadata and base point estimates.",
        analysis="Not tail risk; use /v1/simulate/asset for distributions.",
    ),
)
def simulate_v0_base(
    asset: AssetAssumptions,
    user: str | None = Depends(read_user_id),
) -> BaseCaseResult:
    result = run_v0_base_case(asset, user_id=user)
    audit_simulation("v0_base", result, user_id=user, client_hint="http:v0")
    return result


@app.post(
    "/v1/simulate/portfolio",
    response_model=PortfolioSimulationResult,
    dependencies=[Depends(optional_api_key)],
    summary="Monte Carlo — joint portfolio (≥2 assets)",
    description=_ep(
        desc="One shock draw per scenario shared across all assets — portfolio breach and min DSCR.",
        send="PortfolioSimulationRequest: shockpack or catalogue id, portfolio ids, assets[].",
        get="per_asset metrics + portfolio block (any breach, min DSCR, concentration, CF tails).",
        analysis="Joint probability differs from sum of silo runs because factors are correlated across names.",
    ),
)
def simulate_portfolio(
    req: PortfolioSimulationRequest,
    user: str | None = Depends(read_user_id),
) -> PortfolioSimulationResult:
    sp, cid = resolve_shockpack_for_request(req.shockpack, req.shockpack_catalog_entry_id)
    result = run_portfolio_joint_simulation(
        sp,
        req.portfolio_id,
        req.portfolio_assumption_set_id,
        req.assets,
        user_id=user,
        performance_profile=req.performance_profile,
        shockpack_catalog_entry_id=cid,
    )
    audit_simulation("portfolio_joint", result, user_id=user, client_hint="http:portfolio")
    return result


@app.post(
    "/v1/shockpack/catalog/register",
    dependencies=[Depends(optional_api_key)],
    summary="Register ShockPackSpec in catalogue",
    description=_ep(
        desc="Persist shock pack for reuse via shockpack_catalog_entry_id.",
        send="ShockPackSpec body; query semver, tenant_id, promotion_tier, rbac_owner_role.",
        get="{ entry_id } UUID string.",
        analysis="Reduces paste errors; simulate can patch fields on top of a registered pack.",
    ),
)
def shockpack_catalog_register(
    spec: ShockPackSpec,
    semver: str = "1.0.0",
    tenant_id: str | None = None,
    promotion_tier: Literal["dev", "staging", "prod"] = "dev",
    rbac_owner_role: str = "editor",
) -> dict[str, str]:
    """§6.3 — persist ShockPackSpec JSON for reuse via shockpack_catalog_entry_id."""
    eid = register_spec(
        spec,
        semver=semver,
        tenant_id=tenant_id,
        promotion_tier=promotion_tier,
        rbac_owner_role=rbac_owner_role,
    )
    return {"entry_id": eid, "response_help": dict(CATALOG_REGISTER)}


@app.post(
    "/v1/shockpack/catalog/{entry_id}/promote",
    dependencies=[Depends(optional_api_key), Depends(require_catalog_promoter)],
    summary="Promote catalogue entry tier",
    description=_ep(
        desc="Set promotion_tier (dev/staging/prod) for governance.",
        send="entry_id path + to_tier query; X-Azraq-Catalog-Role unless AZRAQ_CATALOG_PROMOTER_ROLES is empty.",
        get="{ ok: true } or 403.",
        analysis="Filter list endpoint by promotion_tier=prod for approved packs only.",
    ),
)
def shockpack_catalog_promote(
    entry_id: str,
    to_tier: Literal["dev", "staging", "prod"],
) -> dict[str, bool]:
    """Promotion dev → staging → prod (requires X-Azraq-Catalog-Role allow-list)."""
    promote_entry(entry_id, to_tier)
    return {"ok": True, "response_help": dict(CATALOG_PROMOTE)}


@app.get(
    "/v1/shockpack/catalog/{entry_id}",
    dependencies=[Depends(optional_api_key)],
    summary="Get catalogue entry + spec",
    description=_ep(
        desc="Fetch full registered ShockPackSpec and metadata.",
        send="entry_id; optional X-Azraq-Tenant-Id must match stored tenant if enforced.",
        get="Catalogue row including spec JSON.",
        analysis="Inspect exact inputs before running simulate.",
    ),
)
def shockpack_catalog_get(
    entry_id: str,
    tenant: str | None = Depends(read_tenant_id),
) -> dict[str, object]:
    try:
        row = load_entry(entry_id, tenant_id=tenant, enforce_tenant=bool(tenant))
        row = dict(row)
        row["response_help"] = dict(CATALOG_ENTRY)
        return row
    except PermissionError:
        raise HTTPException(status_code=403, detail="Catalog entry tenant does not match X-Azraq-Tenant-Id")


@app.get(
    "/v1/shockpack/catalog",
    dependencies=[Depends(optional_api_key)],
    summary="List catalogue entries",
    description=_ep(
        desc="Recent shockpack registrations (metadata; use GET by id for full spec).",
        send="Query limit, tenant_id, promotion_tier; header tenant may filter.",
        get="{ entries: [...] }.",
        analysis="Discover entry_id values for automation.",
    ),
)
def shockpack_catalog_list(
    limit: int = 100,
    tenant_id: str | None = None,
    promotion_tier: Literal["dev", "staging", "prod"] | None = None,
    _tenant: str | None = Depends(read_tenant_id),
) -> dict[str, list]:
    tid = tenant_id if tenant_id is not None else _tenant
    return {
        "entries": list_entries(limit=limit, tenant_id=tid, promotion_tier=promotion_tier),
        "response_help": dict(CATALOG_LIST),
    }


@app.post(
    "/v1/shockpack/export/npz",
    dependencies=[Depends(optional_api_key)],
    summary="Export shocks to NumPy .npz on disk",
    description=_ep(
        desc="Writes correlated Z scenarios to filesystem for offline use.",
        send="ShockExportRequest: shockpack + optional directory.",
        get="{ path } to .npz file.",
        analysis="No financial metrics here — only random draws; interpretation needs your downstream code.",
    ),
)
def shockpack_export_npz(req: ShockExportRequest) -> dict[str, str]:
    spec_resolved, _ = materialize_shockpack_margins(req.shockpack)
    shocks = build_shock_array(spec_resolved)
    path = save_shockpack_npz(_shock_export_root(req.directory), spec_resolved, shocks)
    return {"path": str(path.resolve()), "response_help": dict(SHOCK_EXPORT_NPZ)}


@app.post(
    "/v1/snapshots/save",
    dependencies=[Depends(optional_api_key)],
    summary="Save simulation result JSON to disk",
    description=_ep(
        desc="Persist a prior SimulationResult / Portfolio / BaseCase to snapshots folder.",
        send="SnapshotSaveRequest: label optional + full result object.",
        get="{ path } to saved JSON.",
        analysis="Bookmark runs or feed external diff/dashboard tools.",
    ),
)
def snapshot_save(req: SnapshotSaveRequest) -> dict[str, str]:
    root = _snapshot_root()
    if isinstance(req.result, PortfolioSimulationResult):
        kind = "portfolio_simulation"
    elif isinstance(req.result, BaseCaseResult):
        kind = "v0_base"
    else:
        kind = "asset_simulation"
    path = save_snapshot(root, kind, req.result, label=req.label)
    return {"path": str(path.resolve()), "response_help": dict(SNAPSHOT_SAVE)}


@app.get(
    "/v1/snapshots/list",
    dependencies=[Depends(optional_api_key)],
    summary="List saved snapshot paths",
    description=_ep(
        desc="Paths under AZRAQ_SNAPSHOT_DIR for prior saved runs.",
        send="Optional API key only.",
        get="{ paths: [ ... ] } absolute paths.",
        analysis="Use paths as before_path/after_path in snapshots/diff.",
    ),
)
def snapshot_list() -> dict[str, object]:
    paths = list_snapshots(_snapshot_root())
    return {"paths": [str(p.resolve()) for p in paths], "response_help": dict(SNAPSHOT_LIST)}


@app.get(
    "/v1/audit/runs",
    dependencies=[Depends(optional_api_key)],
    summary="Recent audited simulation runs",
    description=_ep(
        desc="SQLite audit log rows for HTTP/WS simulate calls (if audit enabled).",
        send="Query limit (default 50).",
        get="{ runs: [ { run_id, run_kind, asset_id, … }, … ] }.",
        analysis="Tie HTTP activity to SimulationResult.metadata.run_id for compliance.",
    ),
)
def audit_runs(limit: int = 50) -> dict[str, object]:
    return {"runs": fetch_recent_runs(limit=limit), "response_help": dict(AUDIT_RUNS)}


class SnapshotDiffBody(BaseModel):
    before_path: str
    after_path: str


@app.post(
    "/v1/snapshots/diff/asset-metrics",
    dependencies=[Depends(optional_api_key)],
    summary="Diff two asset SimulationResult snapshots",
    description=_ep(
        desc="Metrics delta + provenance delta (what assumption/shock inputs changed).",
        send="JSON before_path and after_path (server filesystem paths).",
        get="metrics_delta, provenance_delta, response_help; 400 if not both asset SimulationResult.",
        analysis="Explain metric drift: assumptions vs shockpack vs seed vs catalogue vs model version.",
    ),
)
def snapshot_diff_asset(body: SnapshotDiffBody) -> dict:
    b = load_snapshot_typed(body.before_path)
    a = load_snapshot_typed(body.after_path)
    if not isinstance(b, SimulationResult) or not isinstance(a, SimulationResult):
        raise HTTPException(status_code=400, detail="both snapshots must be asset_simulation")
    return diff_simulation_results(b, a)


@app.websocket("/ws/v1/simulate/portfolio")
async def ws_simulate_portfolio(ws: WebSocket) -> None:
    await ws.accept()
    need = os.environ.get("AZRAQ_API_KEY")
    if need and ws.headers.get("x-api-key") != need:
        await ws.send_json({"type": "error", "detail": "Unauthorized"})
        await ws.close(code=4401)
        return
    try:
        payload = await ws.receive_json()
        req = PortfolioSimulationRequest.model_validate(payload)
        progress_log: list[tuple[int, int]] = []

        def prog(i: int, n: int) -> None:
            progress_log.append((i, n))

        def work() -> PortfolioSimulationResult:
            sp, cid = resolve_shockpack_for_request(req.shockpack, req.shockpack_catalog_entry_id)
            return run_portfolio_joint_simulation(
                sp,
                req.portfolio_id,
                req.portfolio_assumption_set_id,
                req.assets,
                progress=prog,
                performance_profile=req.performance_profile,
                shockpack_catalog_entry_id=cid,
            )

        res = await asyncio.to_thread(work)
        for done, of in progress_log:
            await ws.send_json({"type": "progress", "done": done, "of": of})
        await ws.send_json({"type": "result", "body": res.model_dump(mode="json")})
        audit_simulation("portfolio_joint_ws", res, client_hint="ws:portfolio")
    except Exception as e:  # noqa: BLE001
        await ws.send_json({"type": "error", "detail": str(e)})
    finally:
        await ws.close()


_frontend_dir = _ROOT / "frontend"
if _frontend_dir.is_dir():
    app.mount(
        "/app",
        StaticFiles(directory=str(_frontend_dir), html=True),
        name="v0_frontend",
    )
