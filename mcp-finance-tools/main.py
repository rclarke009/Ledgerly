"""FastAPI app exposing MCP finance tools (calculations + optional Finnhub quotes)."""

from fastapi import FastAPI, HTTPException
from fastapi_mcp import FastApiMCP

from tools.finance import (
    CompoundInput,
    CompoundOutput,
    calculate_compound_interest,
)
from tools.market import (
    MarketDataError,
    StockQuoteInput,
    StockQuoteOutput,
    fetch_stock_quote,
)
from tools.rates import (
    CompareRateDeltaInput,
    CompareRateDeltaOutput,
    SafeYieldBenchmarksOutput,
    SimpleInterestInput,
    SimpleInterestOutput,
    compare_rate_delta,
    calculate_simple_interest,
    get_safe_yield_benchmarks,
)

app = FastAPI(
    title="Ledgerly Finance MCP Tools",
    description=(
        "MCP server for local AI advisors (e.g. Ledgerly app). "
        "Safe-yield benchmarks from FRED Treasury series (no user PII sent). "
        "Calculation tools run locally. "
        "Optional Finnhub stock quotes when FINNHUB_API_KEY is set."
    ),
    version="0.3.0",
)


@app.post(
    "/tools/calculate_compound_interest",
    response_model=CompoundOutput,
    operation_id="calculate_compound_interest",
)
def compound_interest_endpoint(input_data: CompoundInput) -> CompoundOutput:
    """
    MCP Tool: Calculate compound interest.

    Use this when the user asks about investment growth, savings projections,
    or \"how much will $X grow to in Y years at Z%\". Return concise results
    unless a detailed breakdown is requested.
    """
    result = calculate_compound_interest(
        principal=input_data.principal,
        rate=input_data.rate,
        years=input_data.years,
    )
    return CompoundOutput(**result)


@app.post(
    "/tools/calculate_simple_interest",
    response_model=SimpleInterestOutput,
    operation_id="calculate_simple_interest",
)
def simple_interest_endpoint(input_data: SimpleInterestInput) -> SimpleInterestOutput:
    """
    MCP Tool: Calculate simple interest for CD-style terms.

    Use for \"how much interest on $X at Y% for Z years\" with rate as decimal (0.045 = 4.5%).
    """
    try:
        return calculate_simple_interest(
            principal=input_data.principal,
            rate=input_data.rate,
            years=input_data.years,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post(
    "/tools/get_safe_yield_benchmarks",
    response_model=SafeYieldBenchmarksOutput,
    operation_id="get_safe_yield_benchmarks",
)
def safe_yield_benchmarks_endpoint() -> SafeYieldBenchmarksOutput:
    """
    MCP Tool: Current safe-yield benchmarks (Treasury proxies for CD terms and MMF).

    Uses FRED when FRED_API_KEY is set; otherwise returns curated fallback tiers.
    No user data is sent to external APIs — only public Treasury series IDs.
    """
    return get_safe_yield_benchmarks()


@app.post(
    "/tools/compare_rate_delta",
    response_model=CompareRateDeltaOutput,
    operation_id="compare_rate_delta",
)
def compare_rate_delta_endpoint(input_data: CompareRateDeltaInput) -> CompareRateDeltaOutput:
    """
    MCP Tool: Compare a holding APY percent to a benchmark APY percent.

    Returns delta, whether the gap is meaningful (default 0.25%), and a short summary.
    """
    return compare_rate_delta(
        user_rate_apr=input_data.user_rate_apr,
        benchmark_rate_apr=input_data.benchmark_rate_apr,
        meaningful_delta=input_data.meaningful_delta,
    )


@app.post(
    "/tools/get_stock_quote",
    response_model=StockQuoteOutput,
    operation_id="get_stock_quote",
)
def get_stock_quote_endpoint(input_data: StockQuoteInput) -> StockQuoteOutput:
    """
    MCP Tool: Current stock / ETF quote via Finnhub.

    Use for \"what is AAPL at\", \"current price of SPY\", etc.
    Requires FINNHUB_API_KEY in .env or the environment. Do not invent prices; call this tool.
    """
    try:
        return fetch_stock_quote(input_data.symbol)
    except MarketDataError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


mcp = FastApiMCP(
    app,
    name="Ledgerly Finance Tools",
    description=(
        "Safe-yield benchmarks (FRED Treasury proxies), local financial calculations, "
        "and optional Finnhub quotes. For CD/MMF comparisons use get_safe_yield_benchmarks; "
        "do not guess rates. Set FRED_API_KEY for live benchmarks; FINNHUB_API_KEY for quotes."
    ),
)
mcp.mount_http()

if __name__ == "__main__":
    import os

    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    # Dev only: reload. Docker image uses uvicorn without reload.
    dev = os.environ.get("FINANCE_MCP_DEV", "").strip().lower() in ("1", "true", "yes")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=dev)
