from __future__ import annotations

import json

from fastapi.testclient import TestClient

from azraq_mc.api import app


def test_calibration_preview_no_dynamic(monkeypatch):
    monkeypatch.delenv("AZRAQ_API_KEY", raising=False)
    client = TestClient(app)
    body = {"shockpack_id": "prev-1", "seed": 7, "n_scenarios": 500, "margins": {"revenue_log_sigma": 0.09}}
    r = client.post("/v1/calibration/preview", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["calibration_trace"] is None
    assert data["resolved_shockpack"]["margins"]["revenue_log_sigma"] == 0.09
    assert data["resolved_shockpack"]["dynamic_margins"] is None


def test_calibration_preview_with_file(tmp_path, monkeypatch):
    monkeypatch.delenv("AZRAQ_API_KEY", raising=False)
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"revenue_log_sigma": 0.22}), encoding="utf-8")
    client = TestClient(app)
    body = {
        "shockpack_id": "prev-2",
        "seed": 7,
        "n_scenarios": 500,
        "dynamic_margins": {"file": {"path": str(p), "mode": "overlay"}},
    }
    r = client.post("/v1/calibration/preview", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["resolved_shockpack"]["margins"]["revenue_log_sigma"] == 0.22
    assert data["resolved_shockpack"]["dynamic_margins"] is None
    assert data["calibration_trace"] is not None
    assert data["calibration_trace"]["steps"]
