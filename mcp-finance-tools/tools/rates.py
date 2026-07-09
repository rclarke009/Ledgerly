"""FRED-backed safe-yield benchmarks and local rate helpers for MCP tools."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import requests
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"
DEFAULT_TIMEOUT_SEC = 15

# Treasury constant maturity as CD-term proxy (public series IDs only — no PII).
CD_SERIES: list[tuple[int, str, str]] = [
    (3, "DGS3MO", "3-Month Treasury (CD proxy)"),
    (6, "DGS6MO", "6-Month Treasury (CD proxy)"),
    (12, "DGS1", "1-Year Treasury (CD proxy)"),
    (24, "DGS2", "2-Year Treasury (CD proxy)"),
]
MMF_SERIES = ("DGS3MO", "3-Month Treasury (MMF proxy)")

# Static fallback when FRED is unavailable (matches Ledgerly defaults).
CURATED_CD_BENCHMARKS: list[tuple[int, float, str]] = [
    (3, 4.15, "3-month CD benchmark"),
    (6, 4.25, "6-month CD benchmark"),
    (12, 4.35, "12-month CD benchmark"),
    (24, 4.10, "24-month CD benchmark"),
]
CURATED_MMF_APR = 4.50
CURATED_MMF_LABEL = "Money market fund benchmark (curated fallback)"

_cache_payload: dict[str, Any] | None = None
_cache_expires_at: float = 0.0


class BenchmarkEntry(BaseModel):
    product_type: str = Field(description="cd or mmf")
    term_months: int | None = None
    rate_apr: float
    label: str
    source_name: str
    source_url: str | None = None
    as_of: str | None = None
    quote: str | None = None


class SafeYieldBenchmarksOutput(BaseModel):
    benchmarks: list[BenchmarkEntry]
    mmf_proxy: BenchmarkEntry | None = None
    source: str = Field(description="fred | curated_fallback")
    fetched_at: str


class CompareRateDeltaInput(BaseModel):
    user_rate_apr: float = Field(..., description="User holding APY as percent, e.g. 4.85")
    benchmark_rate_apr: float = Field(..., description="Benchmark APY as percent, e.g. 5.1")
    meaningful_delta: float = Field(
        default=0.25,
        description="Minimum absolute delta (percent points) to flag as meaningful",
    )


class CompareRateDeltaOutput(BaseModel):
    user_rate: float
    benchmark_rate: float
    delta: float
    meaningful: bool
    summary: str


class SimpleInterestInput(BaseModel):
    principal: float = Field(..., description="Initial amount, e.g. 10000")
    rate: float = Field(..., description="Annual rate as decimal, e.g. 0.045 for 4.5%")
    years: float = Field(..., description="Term in years, e.g. 1.0 for 12 months")


class SimpleInterestOutput(BaseModel):
    final_amount: float
    total_interest: float
    principal: float
    rate_decimal: float
    years: float


def _fred_api_key() -> str:
    return (os.environ.get("FRED_API_KEY") or "").strip()


def _cache_ttl_sec() -> int:
    raw = (os.environ.get("RATE_CACHE_TTL_SEC") or "21600").strip()
    try:
        return max(60, int(raw))
    except ValueError:
        return 21600


def _fred_series_url(series_id: str) -> str:
    return f"https://fred.stlouisfed.org/series/{series_id}"


def _fetch_fred_latest(series_id: str) -> tuple[float, str] | None:
    """Return (rate_apr_percent, observation_date) for the latest non-missing observation."""
    key = _fred_api_key()
    if not key:
        return None
    params = {
        "series_id": series_id,
        "api_key": key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 10,
    }
    try:
        r = requests.get(FRED_OBSERVATIONS_URL, params=params, timeout=DEFAULT_TIMEOUT_SEC)
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        logger.warning("FRED request failed for %s: %s", series_id, e)
        return None

    observations = data.get("observations")
    if not isinstance(observations, list):
        return None
    for obs in observations:
        if not isinstance(obs, dict):
            continue
        val = obs.get("value")
        date = obs.get("date")
        if val in (None, ".", ""):
            continue
        try:
            rate = float(val)
        except (TypeError, ValueError):
            continue
        if date:
            return rate, str(date)
    return None


def _curated_fallback_payload() -> SafeYieldBenchmarksOutput:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    benchmarks: list[BenchmarkEntry] = []
    for term, rate, label in CURATED_CD_BENCHMARKS:
        benchmarks.append(
            BenchmarkEntry(
                product_type="cd",
                term_months=term,
                rate_apr=rate,
                label=label,
                source_name="Ledgerly curated fallback",
                source_url=None,
                as_of=None,
                quote=f"{label}: ~{rate:.2f}% APY (curated fallback)",
            )
        )
    mmf = BenchmarkEntry(
        product_type="mmf",
        term_months=None,
        rate_apr=CURATED_MMF_APR,
        label=CURATED_MMF_LABEL,
        source_name="Ledgerly curated fallback",
        source_url=None,
        as_of=None,
        quote=f"{CURATED_MMF_LABEL}: ~{CURATED_MMF_APR:.2f}% (curated fallback)",
    )
    return SafeYieldBenchmarksOutput(
        benchmarks=benchmarks,
        mmf_proxy=mmf,
        source="curated_fallback",
        fetched_at=now,
    )


def _fetch_fred_payload() -> SafeYieldBenchmarksOutput | None:
    if not _fred_api_key():
        return None
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    benchmarks: list[BenchmarkEntry] = []
    latest_dates: list[str] = []

    for term_months, series_id, label in CD_SERIES:
        result = _fetch_fred_latest(series_id)
        if result is None:
            return None
        rate, as_of = result
        latest_dates.append(as_of)
        benchmarks.append(
            BenchmarkEntry(
                product_type="cd",
                term_months=term_months,
                rate_apr=round(rate, 4),
                label=label,
                source_name="FRED",
                source_url=_fred_series_url(series_id),
                as_of=as_of,
                quote=f"{label}: ~{rate:.2f}% (FRED {series_id}, as of {as_of})",
            )
        )

    mmf_series_id, mmf_label = MMF_SERIES
    mmf_result = _fetch_fred_latest(mmf_series_id)
    mmf_proxy: BenchmarkEntry | None = None
    if mmf_result is not None:
        mmf_rate, mmf_as_of = mmf_result
        latest_dates.append(mmf_as_of)
        mmf_proxy = BenchmarkEntry(
            product_type="mmf",
            term_months=3,
            rate_apr=round(mmf_rate, 4),
            label=mmf_label,
            source_name="FRED",
            source_url=_fred_series_url(mmf_series_id),
            as_of=mmf_as_of,
            quote=f"{mmf_label}: ~{mmf_rate:.2f}% (FRED {mmf_series_id}, as of {mmf_as_of})",
        )

    if not benchmarks:
        return None

    return SafeYieldBenchmarksOutput(
        benchmarks=benchmarks,
        mmf_proxy=mmf_proxy,
        source="fred",
        fetched_at=now,
    )


def get_safe_yield_benchmarks(*, force_refresh: bool = False) -> SafeYieldBenchmarksOutput:
    """
    Return CD-term and MMF safe-yield benchmarks from FRED, with curated fallback.

    No user data is sent to FRED — only public Treasury series IDs and the API key.
    """
    global _cache_payload, _cache_expires_at

    if not force_refresh and _cache_payload is not None and time.time() < _cache_expires_at:
        return SafeYieldBenchmarksOutput(**_cache_payload)

    payload = _fetch_fred_payload()
    if payload is None:
        payload = _curated_fallback_payload()

    _cache_payload = payload.model_dump()
    _cache_expires_at = time.time() + _cache_ttl_sec()
    return payload


def compare_rate_delta(
    user_rate_apr: float,
    benchmark_rate_apr: float,
    *,
    meaningful_delta: float = 0.25,
) -> CompareRateDeltaOutput:
    """Compare a holding APY (percent) to a benchmark APY (percent)."""
    delta = float(benchmark_rate_apr) - float(user_rate_apr)
    meaningful = abs(delta) >= meaningful_delta
    user = float(user_rate_apr)
    bench = float(benchmark_rate_apr)
    if delta > 0:
        summary = (
            f"Your {user:.2f}% vs benchmark ~{bench:.2f}% "
            f"(market ~{delta:+.2f}%)."
        )
    elif delta < 0:
        summary = (
            f"Your {user:.2f}% is above benchmark ~{bench:.2f}% "
            f"({delta:+.2f}%). Renewal may still be fine if simplicity matters."
        )
    else:
        summary = f"Your {user:.2f}% matches benchmark ~{bench:.2f}%."
    if not meaningful:
        summary += (
            " Difference is small — action threshold: prefer hold/renew unless "
            "liquidity or obligation requires change."
        )
    return CompareRateDeltaOutput(
        user_rate=user,
        benchmark_rate=bench,
        delta=round(delta, 4),
        meaningful=meaningful,
        summary=summary,
    )


def calculate_simple_interest(
    principal: float,
    rate: float,
    years: float,
) -> SimpleInterestOutput:
    """Simple interest: I = P * r * t. Rate is annual decimal."""
    from decimal import Decimal, getcontext

    getcontext().prec = 10
    if years < 0 or rate < 0 or principal <= 0:
        raise ValueError("principal > 0, rate >= 0, years >= 0 required")
    p = Decimal(str(principal))
    r = Decimal(str(rate))
    t = Decimal(str(years))
    interest = p * r * t
    final_amount = p + interest
    return SimpleInterestOutput(
        final_amount=float(final_amount.quantize(Decimal("0.01"))),
        total_interest=float(interest.quantize(Decimal("0.01"))),
        principal=principal,
        rate_decimal=rate,
        years=years,
    )


def clear_rate_cache() -> None:
    """Clear in-memory benchmark cache (for tests)."""
    global _cache_payload, _cache_expires_at
    _cache_payload = None
    _cache_expires_at = 0.0
