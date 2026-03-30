from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, WebSocket
from pydantic import BaseModel

from azraq_mc.api_audit import audit_simulation
from azraq_mc.api_deps import optional_api_key, read_user_id
from azraq_mc.api_schemas import (
    AdhocSimulationRequest,
    PortfolioSimulationRequest,
    ScheduledAssetRequest,
    ScheduledAssetResponse,
    ShockExportRequest,
    SnapshotSaveRequest,
)
from azraq_mc.audit import fetch_recent_runs
from azraq_mc.engine import run_adhoc_asset_simulation
from azraq_mc.presets import FULL_STACK_FACTOR_ORDER, FULL_STACK_RISK_FACTOR_CATALOG
from azraq_mc.io_shockpack import save_shockpack_npz
from azraq_mc.monitoring import run_scheduled_asset_simulation
from azraq_mc.portfolio import run_portfolio_joint_simulation
from azraq_mc.schemas import AssetAssumptions, BaseCaseResult, PortfolioSimulationResult, SimulationResult
from azraq_mc.shockpack import build_shock_array
from azraq_mc.snapshots import diff_simulation_results, list_snapshots, load_snapshot_typed, save_snapshot
from azraq_mc.v0 import run_v0_base_case

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

app = FastAPI(title="Azraq Monte Carlo Risk Engine", version="1.0")


def _snapshot_root() -> Path:
    return Path(os.environ.get("AZRAQ_SNAPSHOT_DIR", "data/snapshots"))


def _shock_export_root(req_dir: str | None) -> Path:
    if req_dir:
        return Path(req_dir)
    return Path(os.environ.get("AZRAQ_SHOCK_EXPORT_DIR", "data/shockpacks"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/catalog/full-stack-factors", dependencies=[Depends(optional_api_key)])
def catalog_full_stack_factors() -> dict[str, object]:
    return {
        "factor_order": list(FULL_STACK_FACTOR_ORDER),
        "risk_factors": [rf.model_dump(mode="json") for rf in FULL_STACK_RISK_FACTOR_CATALOG],
    }


@app.post(
    "/v1/simulate/scheduled/asset",
    response_model=ScheduledAssetResponse,
    dependencies=[Depends(optional_api_key)],
)
def simulate_scheduled_asset(
    req: ScheduledAssetRequest,
    user: str | None = Depends(read_user_id),
) -> ScheduledAssetResponse:
    result, path = run_scheduled_asset_simulation(
        req.shockpack,
        req.asset,
        snapshot_root=_snapshot_root(),
        label=req.label,
        persist=req.persist,
        model_version=req.model_version,
        include_attribution=req.include_attribution,
        user_id=user,
    )
    audit_simulation("scheduled_monitoring", result, user_id=user, client_hint="http:scheduled")
    return ScheduledAssetResponse(
        result=result,
        snapshot_path=str(path.resolve()) if path is not None else None,
    )


@app.post("/v1/simulate/asset", response_model=SimulationResult, dependencies=[Depends(optional_api_key)])
def simulate_asset(
    req: AdhocSimulationRequest,
    user: str | None = Depends(read_user_id),
) -> SimulationResult:
    result = run_adhoc_asset_simulation(
        req.shockpack,
        req.asset,
        include_attribution=req.include_attribution,
        attribution_tail_fraction=req.attribution_tail_fraction,
        user_id=user,
    )
    audit_simulation("adhoc_asset", result, user_id=user, client_hint="http:asset")
    return result


@app.post("/v1/simulate/v0/base-case", response_model=BaseCaseResult, dependencies=[Depends(optional_api_key)])
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
)
def simulate_portfolio(
    req: PortfolioSimulationRequest,
    user: str | None = Depends(read_user_id),
) -> PortfolioSimulationResult:
    result = run_portfolio_joint_simulation(
        req.shockpack,
        req.portfolio_id,
        req.portfolio_assumption_set_id,
        req.assets,
        user_id=user,
    )
    audit_simulation("portfolio_joint", result, user_id=user, client_hint="http:portfolio")
    return result


@app.post(
    "/v1/shockpack/export/npz",
    dependencies=[Depends(optional_api_key)],
)
def shockpack_export_npz(req: ShockExportRequest) -> dict[str, str]:
    shocks = build_shock_array(req.shockpack)
    path = save_shockpack_npz(_shock_export_root(req.directory), req.shockpack, shocks)
    return {"path": str(path.resolve())}


@app.post("/v1/snapshots/save", dependencies=[Depends(optional_api_key)])
def snapshot_save(req: SnapshotSaveRequest) -> dict[str, str]:
    root = _snapshot_root()
    if isinstance(req.result, PortfolioSimulationResult):
        kind = "portfolio_simulation"
    elif isinstance(req.result, BaseCaseResult):
        kind = "v0_base"
    else:
        kind = "asset_simulation"
    path = save_snapshot(root, kind, req.result, label=req.label)
    return {"path": str(path.resolve())}


@app.get("/v1/snapshots/list", dependencies=[Depends(optional_api_key)])
def snapshot_list() -> dict[str, list[str]]:
    paths = list_snapshots(_snapshot_root())
    return {"paths": [str(p.resolve()) for p in paths]}


@app.get("/v1/audit/runs", dependencies=[Depends(optional_api_key)])
def audit_runs(limit: int = 50) -> dict[str, list]:
    return {"runs": fetch_recent_runs(limit=limit)}


class SnapshotDiffBody(BaseModel):
    before_path: str
    after_path: str


@app.post("/v1/snapshots/diff/asset-metrics", dependencies=[Depends(optional_api_key)])
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
            return run_portfolio_joint_simulation(
                req.shockpack,
                req.portfolio_id,
                req.portfolio_assumption_set_id,
                req.assets,
                progress=prog,
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
