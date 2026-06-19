import pytest

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

    infos = await fetch_cd_rates()
    assert len(infos) >= 4
    cds = [i for i in infos if i.product_type == "cd" and i.rate_apr is not None]
    assert cds
