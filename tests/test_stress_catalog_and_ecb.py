"""Stress data catalogue (Appendix J) and ECB FX helper."""
from __future__ import annotations

from io import BytesIO
from unittest.mock import patch

from azraq_mc.market_data import ecb_eur_usd_daily
from azraq_mc.stress_data_catalog import catalog_integration_overview, stress_data_catalog

_SAMPLE_ECB_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
                 xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <gesmes:subject>Reference rates</gesmes:subject>
  <Cube>
    <Cube time="2024-06-01">
      <Cube currency="USD" rate="1.08"/>
      <Cube currency="JPY" rate="160.0"/>
    </Cube>
  </Cube>
</gesmes:Envelope>
"""


def test_stress_catalog_covers_appendix_j_scale():
    src = stress_data_catalog()
    assert len(src) >= 24
    ids = {r["id"] for r in src}
    assert "copper_price" in ids and "sofr" in ids and "usd_eur_fx" in ids
    ov = catalog_integration_overview()
    assert "yahoo_finance" in ov and "ecb_eur_usd" in ov and "http_json_overlay" in ov


def test_ecb_parse_with_mocked_fetch():
    class _Resp:
        def read(self):
            return _SAMPLE_ECB_XML

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

    with patch("azraq_mc.market_data.urlopen", return_value=_Resp()):
        out = ecb_eur_usd_daily()
    assert out["one_eur_in_usd"] == 1.08
    assert out["rate_date"] == "2024-06-01"
