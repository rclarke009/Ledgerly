import pytest
from unittest.mock import patch

from app.reference_data import (
    compare_user_rate,
    _parse_reference_cd_rates_env,
    _rate_infos_from_benchmarks,
    RateInfo,
)


def test_parse_reference_cd_rates_env_empty_uses_defaults():
    benchmarks = _parse_reference_cd_rates_env("")
    assert len(benchmarks) >= 3


def test_parse_reference_cd_rates_env_custom():
    raw = '[{"term_months": 6, "rate_apr": 5.0, "label": "Test 6mo"}]'
    benchmarks = _parse_reference_cd_rates_env(raw)
    assert benchmarks == [(6, 5.0, "Test 6mo")]


def test_compare_user_rate_meaningful_delta():
    bench = RateInfo(
        quote="test",
        rate_apr=5.0,
        product_type="cd",
        term_months=12,
    )
    result = compare_user_rate(4.5, bench, meaningful_delta=0.25)
    assert result["meaningful"] is True
    assert result["delta"] == pytest.approx(0.5)


def test_compare_user_rate_small_delta_not_meaningful():
    bench = RateInfo(quote="test", rate_apr=4.6, product_type="cd", term_months=12)
    result = compare_user_rate(4.5, bench, meaningful_delta=0.25)
    assert result["meaningful"] is False


@pytest.mark.asyncio
async def test_fetch_cd_rates_returns_benchmarks():
    from app.reference_data import fetch_cd_rates

    infos = await fetch_cd_rates(include_external=False)
    assert len(infos) >= 4
    cds = [i for i in infos if i.product_type == "cd" and i.rate_apr is not None]
    assert cds


def test_rate_infos_from_mcp_payload():
    from app.reference_data import _rate_infos_from_mcp_payload

    data = {
        "source": "fred",
        "benchmarks": [
            {
                "product_type": "cd",
                "term_months": 12,
                "rate_apr": 4.82,
                "label": "1-Year Treasury (CD proxy)",
                "source_name": "FRED",
                "source_url": "https://fred.stlouisfed.org/series/DGS1",
                "quote": "1-Year Treasury: ~4.82%",
            }
        ],
        "mmf_proxy": {
            "product_type": "mmf",
            "rate_apr": 4.55,
            "label": "3-Month Treasury (MMF proxy)",
            "source_name": "FRED",
        },
    }
    infos = _rate_infos_from_mcp_payload(data)
    assert len(infos) == 2
    cd = next(i for i in infos if i.product_type == "cd")
    assert cd.rate_apr == pytest.approx(4.82)
    assert cd.source_name == "FRED"


@pytest.mark.asyncio
async def test_fetch_cd_rates_from_mcp_mock():
    from app import reference_data

    mcp_response = {
        "source": "fred",
        "benchmarks": [
            {
                "product_type": "cd",
                "term_months": 12,
                "rate_apr": 5.1,
                "label": "1-Year Treasury (CD proxy)",
                "source_name": "FRED",
                "quote": "test",
            }
        ],
        "mmf_proxy": {
            "product_type": "mmf",
            "rate_apr": 4.9,
            "label": "MMF proxy",
            "source_name": "FRED",
        },
    }

    class MockResponse:
        status_code = 200

        def json(self):
            return mcp_response

    class MockClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, json=None):
            return MockResponse()

    with patch.object(reference_data, "FINANCE_TOOLS_BASE_URL", "http://finance-mcp:8000"):
        with patch("app.reference_data.httpx.AsyncClient", return_value=MockClient()):
            infos = await reference_data.fetch_cd_rates(include_external=True)
    assert reference_data.get_rate_source() == "fred"
    assert any(i.rate_apr == pytest.approx(5.1) for i in infos)
