"""Finnhub-backed market data helpers for MCP tools."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import requests
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

FINNHUB_QUOTE_URL = "https://finnhub.io/api/v1/quote"
DEFAULT_TIMEOUT_SEC = 15


class StockQuoteInput(BaseModel):
    """Request body for stock / ETF quote (Finnhub)."""

    symbol: str = Field(
        ...,
        min_length=1,
        description="Ticker symbol, e.g. AAPL, MSFT, SPY (US symbols typical)",
    )

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, v: str) -> str:
        s = v.strip().upper()
        if not s:
            raise ValueError("symbol must not be empty")
        return s


class StockQuoteOutput(BaseModel):
    """Normalized quote for agents (Finnhub quote endpoint)."""

    symbol: str
    price: float
    currency: str | None = Field(
        default=None,
        description="Finnhub quote does not return currency; often USD for US symbols",
    )
    as_of: str | None = Field(
        default=None,
        description="ISO 8601 UTC timestamp from Finnhub last trade time when present",
    )
    source: str = "Finnhub"
    change: float | None = Field(default=None, description="Absolute change vs prior close")
    percent_change: float | None = Field(
        default=None, description="Percent change vs prior close"
    )


class MarketDataError(Exception):
    """Raised when market data cannot be returned."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _finnhub_token() -> str:
    return (os.environ.get("FINNHUB_API_KEY") or "").strip()


def fetch_stock_quote(symbol: str) -> StockQuoteOutput:
    """
    Fetch current quote from Finnhub.

    Raises MarketDataError for configuration, HTTP, or empty data.
    """
    token = _finnhub_token()
    if not token:
        raise MarketDataError(
            "FINNHUB_API_KEY is not set; add it to .env (see .env.example) or the environment.",
            status_code=503,
        )

    sym = (symbol or "").strip().upper()

    params: dict[str, str] = {"symbol": sym, "token": token}
    try:
        r = requests.get(
            FINNHUB_QUOTE_URL,
            params=params,
            timeout=DEFAULT_TIMEOUT_SEC,
        )
        r.raise_for_status()
        data: dict[str, Any] = r.json()
    except requests.RequestException as e:
        logger.warning("Finnhub request failed: %s", e)
        raise MarketDataError(
            f"Finnhub request failed: {e}",
            status_code=502,
        ) from e

    current = data.get("c")
    ts = data.get("t")
    if current is None or ts is None:
        raise MarketDataError(
            f"Unexpected Finnhub response for {sym!r}.",
            status_code=502,
        )

    try:
        price = float(current)
        trade_ts = int(ts)
    except (TypeError, ValueError) as e:
        raise MarketDataError(
            f"Could not parse Finnhub quote for {sym!r}.",
            status_code=502,
        ) from e

    # Finnhub uses 0 for missing / invalid symbol on free tier in practice
    if price <= 0 or trade_ts <= 0:
        raise MarketDataError(
            f"No quote data for {sym}. Check the symbol or try again later.",
            status_code=404,
        )

    as_of = datetime.fromtimestamp(trade_ts, tz=timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )

    change = data.get("d")
    pct = data.get("dp")
    change_f: float | None
    pct_f: float | None
    try:
        change_f = float(change) if change is not None else None
    except (TypeError, ValueError):
        change_f = None
    try:
        pct_f = float(pct) if pct is not None else None
    except (TypeError, ValueError):
        pct_f = None

    return StockQuoteOutput(
        symbol=sym,
        price=price,
        currency=None,
        as_of=as_of,
        source="Finnhub",
        change=change_f,
        percent_change=pct_f,
    )
