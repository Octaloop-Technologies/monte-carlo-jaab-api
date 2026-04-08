from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np

from azraq_mc.schemas import (
    DynamicMarginsSpec,
    RiskFactorMargins,
    ShockPackSpec,
    YahooFinanceVolBinding,
)


def _margin_field_keys() -> set[str]:
    return set(RiskFactorMargins.model_fields.keys())


def _normalize_margin_patch(raw: object) -> dict[str, float]:
    if not isinstance(raw, dict):
        raise ValueError("margin calibration JSON must be an object")
    body = raw
    if "margins" in body and isinstance(body["margins"], dict):
        body = body["margins"]
    allowed = _margin_field_keys()
    out: dict[str, float] = {}
    for k, v in body.items():
        if k in allowed and isinstance(v, (int, float)):
            out[k] = float(v)
    return out


def _apply_margin_patch(current: RiskFactorMargins, patch: dict[str, float], *, replace: bool) -> RiskFactorMargins:
    if replace:
        data = RiskFactorMargins().model_dump()
        data.update(patch)
        return RiskFactorMargins.model_validate(data)
    data = current.model_dump()
    data.update(patch)
    return RiskFactorMargins.model_validate(data)


def _excel_suffix(path: Path) -> bool:
    return path.suffix.lower() in {".xlsx", ".xlsm"}


def _load_margins_from_excel(path: Path, sheet: str | int) -> dict[str, float]:
    try:
        import pandas as pd
    except ImportError as e:
        raise ImportError("pandas is required to read Excel margin files") from e
    try:
        df = pd.read_excel(path, sheet_name=sheet, header=0, engine="openpyxl")
    except ImportError as e:
        raise ImportError(
            "openpyxl is required for .xlsx/.xlsm margin files; install with `pip install openpyxl`"
        ) from e
    if df.empty:
        return {}
    allowed = _margin_field_keys()

    cols = {str(c).strip(): c for c in df.columns}
    lower_map = {str(c).strip().lower(): c for c in df.columns}
    key_aliases = ("key", "field", "margin", "name", "parameter")
    val_aliases = ("value", "sigma", "amount", "val")
    kcol = next((lower_map[a] for a in key_aliases if a in lower_map), None)
    vcol = next((lower_map[a] for a in val_aliases if a in lower_map), None)

    patch: dict[str, float] = {}
    if kcol is not None and vcol is not None:
        for _, row in df.iterrows():
            raw_k = row[kcol]
            if pd.isna(raw_k):
                continue
            k = str(raw_k).strip()
            if k not in allowed:
                continue
            v = row[vcol]
            if pd.isna(v):
                continue
            patch[k] = float(v)
        return patch

    # Wide: header row = RiskFactorMargins field names; first data row supplies values
    row0 = df.iloc[0]
    for c in df.columns:
        k = str(c).strip()
        if k not in allowed:
            continue
        v = row0[c]
        if pd.isna(v):
            continue
        patch[k] = float(v)
    return patch


def _load_margins_from_file(path: str, *, sheet: str | int = 0) -> tuple[dict[str, float], str]:
    p = Path(path).expanduser()
    if not p.is_file():
        raise FileNotFoundError(f"margin calibration file not found: {p}")
    if _excel_suffix(p):
        patch = _load_margins_from_excel(p, sheet)
        return patch, str(p.resolve())
    raw = json.loads(p.read_text(encoding="utf-8"))
    patch = _normalize_margin_patch(raw)
    return patch, str(p.resolve())


def _load_margins_from_http(url: str, timeout_sec: float, headers: dict[str, str]) -> dict[str, float]:
    req = Request(url, headers=headers, method="GET")  # noqa: S310 — caller-controlled URL by design
    try:
        with urlopen(req, timeout=timeout_sec) as resp:  # noqa: S310
            body = resp.read().decode("utf-8")
    except HTTPError as e:
        raise ValueError(f"HTTP margin calibration failed: {e.code} {e.reason}") from e
    except URLError as e:
        raise ValueError(f"HTTP margin calibration failed: {e.reason!s}") from e
    raw = json.loads(body)
    return _normalize_margin_patch(raw)


def _annualised_sigma_from_yahoo(binding: YahooFinanceVolBinding) -> float:
    try:
        import yfinance as yf
    except ImportError as e:
        raise ImportError(
            "yfinance is required for ShockPackSpec.dynamic_margins.yahoo_finance; "
            "install with `pip install yfinance`"
        ) from e

    ticker = yf.Ticker(binding.symbol)
    if binding.history_days is not None:
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=int(binding.history_days))
        hist = ticker.history(start=start.isoformat(), end=(end + timedelta(days=1)).isoformat())
        window = f"last_{binding.history_days}_calendar_days"
    else:
        hist = ticker.history(period=binding.period)
        window = binding.period
    if hist.empty or "Close" not in hist.columns:
        raise ValueError(
            f"no Yahoo Finance history for symbol={binding.symbol!r} window={window!r}"
        )
    close = np.asarray(hist["Close"].astype(float), dtype=np.float64)
    close = close[np.isfinite(close) & (close > 0)]
    if close.size < binding.min_observations + 1:
        raise ValueError(
            f"insufficient Yahoo Finance data for {binding.symbol!r}: got {close.size} points, "
            f"need > {binding.min_observations}"
        )
    lr = np.diff(np.log(close))
    lr = lr[np.isfinite(lr)]
    if lr.size < binding.min_observations:
        raise ValueError(f"insufficient valid log returns for {binding.symbol!r}")
    per_bar = float(np.std(lr, ddof=1))
    annual = per_bar * np.sqrt(binding.annualization_factor)
    return max(annual * binding.scale, 1e-12)


def materialize_shockpack_margins(spec: ShockPackSpec) -> tuple[ShockPackSpec, dict[str, Any] | None]:
    """
    Resolve `dynamic_margins` into concrete `margins`, return a spec copy with `dynamic_margins=None`.
    If `dynamic_margins` is unset, returns `(spec, None)` unchanged.
    """
    dm = spec.dynamic_margins
    if dm is None:
        return spec, None

    trace: dict[str, Any] = {"steps": []}
    margins = spec.margins.model_copy(deep=True)

    if dm.file is not None:
        patch, resolved_path = _load_margins_from_file(dm.file.path, sheet=dm.file.sheet)
        margins = _apply_margin_patch(margins, patch, replace=(dm.file.mode == "replace"))
        fmt = "excel" if _excel_suffix(Path(dm.file.path).expanduser()) else "json"
        trace["steps"].append(
            {
                "source": "file",
                "format": fmt,
                "path": resolved_path,
                "mode": dm.file.mode,
                "keys": list(patch.keys()),
            }
        )

    if dm.http is not None:
        patch = _load_margins_from_http(
            dm.http.url,
            dm.http.timeout_sec,
            dm.http.headers,
        )
        margins = _apply_margin_patch(margins, patch, replace=(dm.http.mode == "replace"))
        trace["steps"].append(
            {
                "source": "http_get",
                "url": dm.http.url,
                "mode": dm.http.mode,
                "keys": list(patch.keys()),
            }
        )

    for bind in dm.yahoo_finance:
        sigma = _annualised_sigma_from_yahoo(bind)
        key = bind.target
        setattr(margins, key, sigma)
        step: dict[str, Any] = {
            "source": "yahoo_finance",
            "symbol": bind.symbol,
            "period": bind.period,
            "target": key,
            "annualized_sigma": sigma,
            "scale": bind.scale,
            "annualization_factor": bind.annualization_factor,
        }
        if bind.history_days is not None:
            step["history_days"] = bind.history_days
        trace["steps"].append(step)

    out = spec.model_copy(deep=True)
    out.margins = margins
    out.dynamic_margins = None
    trace["resolved_margins"] = margins.model_dump()
    return out, trace
