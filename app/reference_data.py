"""Reference CD and money-market rate data (generic; no PII)."""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import FINANCE_TOOLS_BASE_URL, FINANCE_TOOLS_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

# Curated safe-income benchmarks when no live source is configured.
# Override via REFERENCE_CD_RATES JSON env (see app/config.py).
DEFAULT_CD_BENCHMARKS: list[tuple[int, float, str]] = [
    (3, 4.15, "3-month CD benchmark"),
    (6, 4.25, "6-month CD benchmark"),
    (12, 4.35, "12-month CD benchmark"),
    (24, 4.10, "24-month CD benchmark"),
]
DEFAULT_MMF_BENCHMARK_APR = 4.50
DEFAULT_MMF_LABEL = "Money market fund benchmark (e.g. VMFXX class)"


@dataclass
class RateInfo:
    quote: str
    source_url: str | None = None
    source_name: str | None = None
    product_type: str = "cd"
    term_months: int | None = None
    rate_apr: float | None = None


def _parse_reference_cd_rates_env(raw: str) -> list[tuple[int, float, str]]:
    if not raw.strip():
        return list(DEFAULT_CD_BENCHMARKS)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("REFERENCE_CD_RATES is not valid JSON; using defaults")
        return list(DEFAULT_CD_BENCHMARKS)
    if not isinstance(data, list):
        return list(DEFAULT_CD_BENCHMARKS)
    out: list[tuple[int, float, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        term = item.get("term_months")
        rate = item.get("rate_apr")
        label = item.get("label") or f"{term}-month CD benchmark"
        if term is None or rate is None:
            continue
        try:
            out.append((int(term), float(rate), str(label)))
        except (TypeError, ValueError):
            continue
    return out or list(DEFAULT_CD_BENCHMARKS)


def _benchmarks_from_config() -> list[tuple[int, float, str]]:
    from app.config import REFERENCE_CD_RATES

    return _parse_reference_cd_rates_env(REFERENCE_CD_RATES)


_last_rate_source: str = "local_curated"


def get_rate_source() -> str:
    """Source of the most recent benchmark fetch: fred, curated_fallback, or local_curated."""
    return _last_rate_source


def _set_rate_source(source: str) -> None:
    global _last_rate_source
    _last_rate_source = source


def _rate_infos_from_mcp_payload(data: dict[str, Any]) -> list[RateInfo]:
    """Map finance-mcp get_safe_yield_benchmarks JSON to RateInfo list."""
    infos: list[RateInfo] = []
    mcp_source = data.get("source") or "curated_fallback"
    source_label = "FRED via finance-mcp" if mcp_source == "fred" else "Ledgerly curated fallback via finance-mcp"

    for entry in data.get("benchmarks") or []:
        if not isinstance(entry, dict):
            continue
        rate = entry.get("rate_apr")
        if rate is None:
            continue
        quote = entry.get("quote") or (
            f"{entry.get('label', 'CD benchmark')}: ~{float(rate):.2f}% APY"
        )
        infos.append(
            RateInfo(
                quote=str(quote),
                source_name=entry.get("source_name") or source_label,
                source_url=entry.get("source_url"),
                product_type=str(entry.get("product_type") or "cd"),
                term_months=entry.get("term_months"),
                rate_apr=float(rate),
            )
        )

    mmf = data.get("mmf_proxy")
    if isinstance(mmf, dict) and mmf.get("rate_apr") is not None:
        rate = float(mmf["rate_apr"])
        quote = mmf.get("quote") or f"{mmf.get('label', 'MMF proxy')}: ~{rate:.2f}%"
        infos.append(
            RateInfo(
                quote=str(quote),
                source_name=mmf.get("source_name") or source_label,
                source_url=mmf.get("source_url"),
                product_type="mmf",
                term_months=mmf.get("term_months"),
                rate_apr=rate,
            )
        )

    return infos


async def _fetch_benchmarks_via_finance_tools() -> tuple[list[RateInfo], str] | None:
    """Fetch safe-yield benchmarks from finance-mcp (no user PII in request)."""
    if not FINANCE_TOOLS_BASE_URL:
        return None
    try:
        url = f"{FINANCE_TOOLS_BASE_URL.rstrip('/')}/tools/get_safe_yield_benchmarks"
        async with httpx.AsyncClient(timeout=FINANCE_TOOLS_TIMEOUT_SECONDS) as client:
            resp = await client.post(url, json={})
            if resp.status_code != 200:
                logger.debug("finance-mcp benchmarks returned %s", resp.status_code)
                return None
            data = resp.json()
        if not isinstance(data, dict):
            return None
        infos = _rate_infos_from_mcp_payload(data)
        if not infos:
            return None
        source = str(data.get("source") or "curated_fallback")
        return infos, source
    except Exception as e:
        logger.debug("finance-mcp benchmarks fetch skipped: %s", e)
        return None


def _rate_infos_from_benchmarks(benchmarks: list[tuple[int, float, str]]) -> list[RateInfo]:
    from app.config import REFERENCE_MMF_APR

    infos: list[RateInfo] = []
    for term, rate, label in benchmarks:
        infos.append(
            RateInfo(
                quote=f"{label}: ~{rate:.2f}% APY (curated benchmark)",
                source_name="Ledgerly curated benchmark",
                source_url=None,
                product_type="cd",
                term_months=term,
                rate_apr=rate,
            )
        )
    mmf_apr = REFERENCE_MMF_APR
    infos.append(
        RateInfo(
            quote=f"{DEFAULT_MMF_LABEL}: ~{mmf_apr:.2f}% (curated benchmark)",
            source_name="Ledgerly curated benchmark",
            product_type="mmf",
            rate_apr=mmf_apr,
        )
    )
    return infos


def fetch_cd_rates_local() -> list[RateInfo]:
    """Curated CD and MMF benchmarks only — no external API calls."""
    benchmarks = _benchmarks_from_config()
    return _rate_infos_from_benchmarks(benchmarks)


async def fetch_cd_rates(*, include_external: bool = True) -> list[RateInfo]:
    """Return generic CD and MMF benchmark rates (no user data)."""
    if include_external and FINANCE_TOOLS_BASE_URL:
        mcp_result = await _fetch_benchmarks_via_finance_tools()
        if mcp_result is not None:
            infos, source = mcp_result
            _set_rate_source(source)
            return infos

    infos = fetch_cd_rates_local()
    _set_rate_source("local_curated")
    return infos


def persist_rate_snapshots(conn: Any, rate_infos: list[RateInfo]) -> None:
    """Store fetched benchmarks in rate_snapshots for history."""
    from app.db import insert_rate_snapshot

    now = int(time.time())
    for ri in rate_infos:
        if ri.rate_apr is None:
            continue
        insert_rate_snapshot(
            conn,
            str(uuid.uuid4()),
            now,
            ri.product_type,
            ri.rate_apr,
            ri.term_months,
            ri.source_url,
            ri.source_name,
            ri.quote,
        )


def get_cached_rate_snapshots(conn: Any, max_age_sec: int = 86400) -> list[RateInfo]:
    """Return recent DB snapshots if fresh enough."""
    from app.db import get_latest_rate_snapshots

    rows = get_latest_rate_snapshots(conn, limit=20)
    if not rows:
        return []
    newest = max(r[1] for r in rows)
    if int(time.time()) - int(newest) > max_age_sec:
        return []
    out: list[RateInfo] = []
    for row in rows:
        _id, fetched_at, product_type, term_months, rate_apr, source_url, source_name, quote = row
        if rate_apr is None:
            continue
        out.append(
            RateInfo(
                quote=quote or f"{product_type} {rate_apr}%",
                source_url=source_url,
                source_name=source_name,
                product_type=product_type or "cd",
                term_months=term_months,
                rate_apr=float(rate_apr),
            )
        )
    return out


async def fetch_cd_rates_with_cache(
    conn: Any | None = None,
    *,
    include_external: bool = True,
) -> list[RateInfo]:
    """Prefer fresh DB cache; otherwise fetch and optionally persist."""
    if conn is not None:
        cached = get_cached_rate_snapshots(conn)
        if cached:
            return cached
    infos = await fetch_cd_rates(include_external=include_external)
    if conn is not None and infos:
        try:
            persist_rate_snapshots(conn, infos)
        except Exception as e:
            logger.warning("Could not persist rate snapshots: %s", e)
    return infos


def closest_cd_benchmark(
    rate_infos: list[RateInfo], term_months: int | None = None
) -> RateInfo | None:
    """Pick nearest-term CD benchmark from rate list."""
    cds = [r for r in rate_infos if r.product_type == "cd" and r.rate_apr is not None]
    if not cds:
        return None
    if term_months is None:
        return cds[0]
    return min(cds, key=lambda r: abs((r.term_months or 12) - term_months))


def mmf_benchmark(rate_infos: list[RateInfo]) -> RateInfo | None:
    for r in rate_infos:
        if r.product_type == "mmf" and r.rate_apr is not None:
            return r
    return None


def compare_user_rate(
    user_rate: float | None,
    benchmark: RateInfo | None,
    *,
    meaningful_delta: float = 0.25,
) -> dict[str, Any]:
    """Compare holding rate vs benchmark; used in decision memos."""
    if user_rate is None or benchmark is None or benchmark.rate_apr is None:
        return {
            "user_rate": user_rate,
            "benchmark_rate": benchmark.rate_apr if benchmark else None,
            "delta": None,
            "meaningful": False,
            "summary": "Rate comparison unavailable (missing user rate or benchmark).",
        }
    delta = float(benchmark.rate_apr) - float(user_rate)
    meaningful = abs(delta) >= meaningful_delta
    if delta > 0:
        summary = (
            f"Your {user_rate:.2f}% vs benchmark ~{benchmark.rate_apr:.2f}% "
            f"(market ~{delta:+.2f}%)."
        )
    elif delta < 0:
        summary = (
            f"Your {user_rate:.2f}% is above benchmark ~{benchmark.rate_apr:.2f}% "
            f"({delta:+.2f}%). Renewal may still be fine if simplicity matters."
        )
    else:
        summary = f"Your {user_rate:.2f}% matches benchmark ~{benchmark.rate_apr:.2f}%."
    if not meaningful:
        summary += " Difference is small — action threshold: prefer hold/renew unless liquidity or obligation requires change."
    return {
        "user_rate": user_rate,
        "benchmark_rate": benchmark.rate_apr,
        "delta": delta,
        "meaningful": meaningful,
        "summary": summary,
    }
