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

app = FastAPI(
    title="Ledgerly Finance MCP Tools",
    description=(
        "MCP server for local AI advisors (e.g. Ledgerly app). "
        "Calculation tools (e.g. compound interest) run locally. "
        "Market tools call Finnhub when FINNHUB_API_KEY is set (e.g. in .env); "
        "ticker symbols are sent to Finnhub over HTTPS."
    ),
    version="0.2.0",
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
        "Local financial calculations plus optional Finnhub quotes. "
        "For current prices or market data, use get_stock_quote; do not guess. "
        "Set FINNHUB_API_KEY in .env (or environment) for quote tools."
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
