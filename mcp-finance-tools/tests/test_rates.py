"""Tests for FRED-backed safe-yield benchmarks."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tools.rates import (
    clear_rate_cache,
    compare_rate_delta,
    calculate_simple_interest,
    get_safe_yield_benchmarks,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_rate_cache()
    yield
    clear_rate_cache()


def test_curated_fallback_when_no_fred_key():
    with patch("tools.rates._fred_api_key", return_value=""):
        payload = get_safe_yield_benchmarks(force_refresh=True)
    assert payload.source == "curated_fallback"
    assert len(payload.benchmarks) >= 4
    assert payload.mmf_proxy is not None
    assert payload.mmf_proxy.rate_apr == pytest.approx(4.50)


def test_fred_fetch_success():
    def mock_latest(series_id: str):
        rates = {
            "DGS3MO": (4.55, "2026-07-01"),
            "DGS6MO": (4.60, "2026-07-01"),
            "DGS1": (4.82, "2026-07-01"),
            "DGS2": (4.70, "2026-07-01"),
        }
        return rates.get(series_id)

    with patch("tools.rates._fred_api_key", return_value="test-key"):
        with patch("tools.rates._fetch_fred_latest", side_effect=mock_latest):
            payload = get_safe_yield_benchmarks(force_refresh=True)
    assert payload.source == "fred"
    cds = [b for b in payload.benchmarks if b.product_type == "cd"]
    assert len(cds) == 4
    twelve = next(b for b in cds if b.term_months == 12)
    assert twelve.rate_apr == pytest.approx(4.82)
    assert payload.mmf_proxy is not None
    assert payload.mmf_proxy.rate_apr == pytest.approx(4.55)


def test_cache_hit_skips_second_fetch():
    with patch("tools.rates._fred_api_key", return_value="test-key"):
        with patch("tools.rates._fetch_fred_latest", return_value=(4.5, "2026-07-01")) as mock_fetch:
            get_safe_yield_benchmarks(force_refresh=True)
            get_safe_yield_benchmarks(force_refresh=False)
    # 4 CD series + 1 MMF (same DGS3MO) = 5 calls first time only
    assert mock_fetch.call_count == 5


def test_compare_rate_delta_meaningful():
    result = compare_rate_delta(4.5, 5.0, meaningful_delta=0.25)
    assert result.meaningful is True
    assert result.delta == pytest.approx(0.5)
    assert "4.50%" in result.summary


def test_compare_rate_delta_small_gap():
    result = compare_rate_delta(4.5, 4.6, meaningful_delta=0.25)
    assert result.meaningful is False


def test_calculate_simple_interest():
    result = calculate_simple_interest(10000, 0.05, 1.0)
    assert result.total_interest == pytest.approx(500.0)
    assert result.final_amount == pytest.approx(10500.0)


def test_fred_partial_failure_falls_back():
    with patch("tools.rates._fred_api_key", return_value="test-key"):
        with patch("tools.rates._fetch_fred_latest", return_value=None):
            payload = get_safe_yield_benchmarks(force_refresh=True)
    assert payload.source == "curated_fallback"
