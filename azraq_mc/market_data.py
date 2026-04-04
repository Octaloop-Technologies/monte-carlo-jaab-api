from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd

ECB_DAILY_FX_URL = (
    "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
)


def yfinance_history(symbol: str, period: str = "1y") -> dict[str, Any]:
    """OHLCV history from Yahoo Finance; raises ValueError if empty."""
    try:
        import yfinance as yf
    except ImportError as e:
        raise ImportError("Install yfinance: `pip install yfinance`") from e

    ticker = yf.Ticker(symbol)
    data = ticker.history(period=period)
    if data.empty:
        raise ValueError(f"No Yahoo Finance data for symbol={symbol!r} period={period!r}")

    df = data.reset_index()
    tcol = df.columns[0]
    if pd.api.types.is_datetime64_any_dtype(df[tcol]):
        df = df.copy()
        df[tcol] = pd.to_datetime(df[tcol]).dt.strftime("%Y-%m-%d")
    records = df.to_dict(orient="records")
    return {"symbol": symbol, "period": period, "data": records}


def yfinance_close_returns(symbol: str, period: str = "1y") -> dict[str, Any]:
    """Close-to-close simple returns (pct_change) as time series."""
    try:
        import yfinance as yf
    except ImportError as e:
        raise ImportError("Install yfinance: `pip install yfinance`") from e

    ticker = yf.Ticker(symbol)
    data = ticker.history(period=period)
    if data.empty or "Close" not in data.columns:
        raise ValueError(f"No Yahoo Finance close series for symbol={symbol!r} period={period!r}")
    r = data["Close"].pct_change().dropna()
    idx = r.index
    rows = [{"date": str(d)[:10], "return": float(v)} for d, v in zip(idx, r.values)]
    return {"symbol": symbol, "period": period, "returns": rows, "n": len(rows)}


def ecb_eur_usd_daily() -> dict[str, Any]:
    """
    Latest USD reference rate from ECB daily euro foreign exchange reference XML.
    Rate convention: **1 EUR = rate USD** (e.g. rate 1.08 → 1 EUR buys 1.08 USD).
    """
    req = Request(ECB_DAILY_FX_URL, headers={"User-Agent": "azraq-mc/1.0"})
    try:
        with urlopen(req, timeout=45) as resp:  # noqa: S310 — ECB public URL
            raw = resp.read()
    except HTTPError as e:
        raise ValueError(f"ECB HTTP error: {e.code} {e.reason}") from e
    except URLError as e:
        raise ValueError(f"ECB fetch failed: {e.reason!s}") from e

    root = ET.fromstring(raw)
    rate_date: str | None = None
    rate: float | None = None
    for cube in root.iter():
        if not cube.tag.endswith("Cube") or "time" not in cube.attrib:
            continue
        rate_date = cube.attrib["time"]
        for child in cube:
            if child.tag.endswith("Cube") and child.attrib.get("currency") == "USD":
                rate = float(child.attrib["rate"])
                break
        if rate is not None:
            break
    if rate_date is None or rate is None:
        raise ValueError("ECB XML: could not parse USD rate (schema may have changed)")
    return {
        "source": "ecb",
        "source_url": ECB_DAILY_FX_URL,
        "rate_date": rate_date,
        "quote": "EUR/USD",
        "one_eur_in_usd": rate,
    }
