"""Smoke-test all HTTP routes on azraq_mc.api:app (run: python scripts/smoke_test_api.py from repo root)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
from fastapi.testclient import TestClient

load_dotenv(_ROOT / ".env")
if not os.environ.get("AZRAQ_SNAPSHOT_DIR"):
    os.environ["AZRAQ_SNAPSHOT_DIR"] = str(Path(tempfile.mkdtemp(prefix="azraq_api_smoke_")))

from azraq_mc.api import app  # noqa: E402
from azraq_mc.presets import make_full_stack_shockpack  # noqa: E402


def _headers():
    import os

    k = os.environ.get("AZRAQ_API_KEY")
    return {"X-API-Key": k} if k else {}


def _min_asset(aid: str = "api-test-1"):
    return {
        "asset_id": aid,
        "assumption_set_id": "as-smoke",
        "horizon_years": 8,
        "base_revenue_annual": 12e6,
        "base_opex_annual": 5e6,
        "initial_capex": 80e6,
        "equity_fraction": 0.35,
        "tax_rate": 0.0,
        "financing": {
            "debt_principal": 40e6,
            "interest_rate_annual": 0.055,
            "loan_term_years": 12,
            "covenant_dscr": 1.2,
        },
    }


def _min_shock(sid: str = "sp-smoke"):
    return {
        "shockpack_id": sid,
        "seed": 7,
        "n_scenarios": 500,
        "sampling_method": "monte_carlo",
    }


def main() -> None:
    c = TestClient(app)
    h = _headers()
    failures: list[str] = []

    def ok(name: str, r) -> None:
        if r.status_code >= 400:
            failures.append(f"{name}: {r.status_code} {r.text[:500]}")

    # 1 health (no key required)
    r = c.get("/health")
    ok("GET /health", r)
    print("GET /health", r.status_code, r.json())

    # 2 catalog
    r = c.get("/v1/catalog/full-stack-factors", headers=h)
    ok("GET /v1/catalog/full-stack-factors", r)
    print("GET /v1/catalog/full-stack-factors", r.status_code, "keys", list(r.json().keys()) if r.status_code == 200 else r.text[:200])

    r = c.get("/v1/calibration/stress-data-catalog", headers=h)
    ok("GET /v1/calibration/stress-data-catalog", r)
    print(
        "GET /v1/calibration/stress-data-catalog",
        r.status_code,
        "n_sources",
        len(r.json().get("sources", [])) if r.status_code == 200 else None,
    )

    r = c.get("/v1/market/ecb/eur-usd", headers=h)
    ok("GET /v1/market/ecb/eur-usd", r)
    print("GET /v1/market/ecb/eur-usd", r.status_code, r.json().get("one_eur_in_usd") if r.status_code == 200 else r.text[:120])

    # 3 simulate asset
    body = {"shockpack": _min_shock(), "asset": _min_asset(), "include_attribution": True}
    r = c.post("/v1/simulate/asset", json=body, headers=h)
    ok("POST /v1/simulate/asset", r)
    print("POST /v1/simulate/asset", r.status_code, "attribution" in (r.json() if r.status_code == 200 else {}))

    # 4 v0 base
    r = c.post("/v1/simulate/v0/base-case", json=_min_asset("v0-id"), headers=h)
    ok("POST /v1/simulate/v0/base-case", r)
    print("POST /v1/simulate/v0/base-case", r.status_code)

    # 5 portfolio
    sp = _min_shock("sp-port")
    r = c.post(
        "/v1/simulate/portfolio",
        json={
            "shockpack": sp,
            "portfolio_id": "pf-smoke",
            "portfolio_assumption_set_id": "pas-1",
            "assets": [_min_asset("a1"), _min_asset("a2")],
        },
        headers=h,
    )
    ok("POST /v1/simulate/portfolio", r)
    print("POST /v1/simulate/portfolio", r.status_code)

    # 6 scheduled (snapshot under AZRAQ_SNAPSHOT_DIR)
    r = c.post(
        "/v1/simulate/scheduled/asset",
        json={
            "shockpack": _min_shock("sp-sched"),
            "asset": _min_asset("sched-1"),
            "label": "smoke",
            "persist": True,
            "model_version": "azraq-mc-v1",
            "include_attribution": False,
        },
        headers=h,
    )
    ok("POST /v1/simulate/scheduled/asset", r)
    print("POST /v1/simulate/scheduled/asset", r.status_code, r.json().get("snapshot_path") if r.status_code == 200 else "")

    # 7 shock export
    tmp2 = tempfile.mkdtemp(prefix="azraq_shock_")
    r = c.post(
        "/v1/shockpack/export/npz",
        json={"shockpack": _min_shock("sp-exp"), "directory": tmp2},
        headers=h,
    )
    ok("POST /v1/shockpack/export/npz", r)
    print("POST /v1/shockpack/export/npz", r.status_code)

    # 8 snapshot save ×2 (for diff)
    r0 = c.post(
        "/v1/simulate/asset",
        json={"shockpack": _min_shock("sp-save-a"), "asset": _min_asset("save-a")},
        headers=h,
    )
    ok("POST /v1/simulate/asset (for snapshot a)", r0)
    r1 = c.post(
        "/v1/simulate/asset",
        json={"shockpack": _min_shock("sp-save-b"), "asset": _min_asset("save-b")},
        headers=h,
    )
    ok("POST /v1/simulate/asset (for snapshot b)", r1)
    if r0.status_code == 200 and r1.status_code == 200:
        for lab, js in (("smoke-a", r0.json()), ("smoke-b", r1.json())):
            r = c.post("/v1/snapshots/save", json={"label": lab, "result": js}, headers=h)
            ok(f"POST /v1/snapshots/save {lab}", r)
        print("POST /v1/snapshots/save", "x2", "ok")

    # 9 snapshot list
    r = c.get("/v1/snapshots/list", headers=h)
    ok("GET /v1/snapshots/list", r)
    print("GET /v1/snapshots/list", r.status_code, "n_paths", len(r.json().get("paths", [])) if r.status_code == 200 else 0)

    # 10 audit runs
    r = c.get("/v1/audit/runs", params={"limit": 5}, headers=h)
    ok("GET /v1/audit/runs", r)
    print("GET /v1/audit/runs", r.status_code, "runs", len(r.json().get("runs", [])) if r.status_code == 200 else 0)

    # 11 snapshot diff (two paths from list)
    paths = c.get("/v1/snapshots/list", headers=h).json().get("paths", [])
    if len(paths) >= 2:
        r = c.post(
            "/v1/snapshots/diff/asset-metrics",
            json={"before_path": paths[-2], "after_path": paths[-1]},
            headers=h,
        )
        ok("POST /v1/snapshots/diff/asset-metrics", r)
        print("POST /v1/snapshots/diff/asset-metrics", r.status_code)
    else:
        print("POST /v1/snapshots/diff/asset-metrics SKIP (need 2 snapshots)")

    # 12 full-stack asset (12-factor + full_stack enabled)
    fs_sp = json.loads(make_full_stack_shockpack("fs-smoke", seed=11, n_scenarios=400).model_dump_json())
    fs_asset = _min_asset("fs-1")
    fs_asset["full_stack"] = {"enabled": True}
    r = c.post("/v1/simulate/asset", json={"shockpack": fs_sp, "asset": fs_asset}, headers=h)
    ok("POST /v1/simulate/asset (full_stack)", r)
    print("POST /v1/simulate/asset full_stack", r.status_code, "full_stack" in str(r.json()) if r.status_code == 200 else False)

    try:
        hdr = {"x-api-key": h["X-API-Key"]} if h.get("X-API-Key") else {}
        with c.websocket_connect("/ws/v1/simulate/portfolio", headers=hdr) as ws:
            ws.send_json(
                {
                    "shockpack": _min_shock("sp-ws2"),
                    "portfolio_id": "pf-ws2",
                    "portfolio_assumption_set_id": "pas-ws2",
                    "assets": [_min_asset("ws-a1"), _min_asset("ws-a2")],
                }
            )
            msgs = []
            while True:
                m = ws.receive_json()
                msgs.append(m)
                if m.get("type") == "result":
                    break
                if m.get("type") == "error":
                    failures.append(f"WS error: {m}")
                    break
            print("WS /ws/v1/simulate/portfolio", "messages", len(msgs), "last_type", msgs[-1].get("type") if msgs else None)
    except Exception as e:  # noqa: BLE001
        failures.append(f"WebSocket: {e}")

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(" -", f)
        raise SystemExit(1)
    print("\nAll smoke tests passed.")


if __name__ == "__main__":
    main()
