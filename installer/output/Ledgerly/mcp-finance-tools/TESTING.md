# Testing plan (MCP + finance tools)

This document explains how to test:

- **FastAPI tool routes**: `POST /tools/calculate_compound_interest`, `POST /tools/get_stock_quote`
- **MCP endpoint** exposed by `fastapi-mcp` (`/mcp`)

## Prerequisites

- `python3`
- `curl`
- **`FINNHUB_API_KEY`** in **`mcp-finance-tools/.env`** for quote tests (copy from `.env.example`; free key: [Finnhub register](https://finnhub.io/register))
- an MCP-capable client (recommended): **Cursor** or **Claude Desktop**
  - or use the `mcp-remote` bridge via `npx` (Node required)

## Start the server (local)

From the repo root:

```bash
cd mcp-finance-tools
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set FINNHUB_API_KEY=... (required for get_stock_quote tests below)
python main.py
```

Expected:

- HTTP server available at `http://localhost:8000` (use a different `PORT` if Ledgerly’s UI already uses 8000)
- MCP endpoint at `http://localhost:<PORT>/mcp`

**Via Ledgerly `docker compose`:** finance-mcp is mapped to host **`http://localhost:8001`** (see repo `docker-compose.yml`).

## Test 0: Finnhub spike (no server)

```bash
# Uses the same .env as the server (FINNHUB_API_KEY=...)
python scripts/spike_finnhub.py AAPL
```

Expected: JSON with Finnhub quote fields (e.g. `c` current price, `t` timestamp).

## Test 1: FastAPI docs load

Open (adjust port if needed):

- `http://localhost:8001/docs` when testing against Docker-mapped finance-mcp, or `http://localhost:8000/docs` for standalone `python main.py`

Expected:

- `POST /tools/calculate_compound_interest` and `POST /tools/get_stock_quote`
- Schemas: `CompoundInput` (`principal`, `rate`, `years`), `StockQuoteInput` (`symbol`)

## Test 2: Compound interest (happy path)

```bash
curl -sS \
  -X POST "http://localhost:8000/tools/calculate_compound_interest" \
  -H "Content-Type: application/json" \
  -d '{"principal":10000,"rate":0.05,"years":10}'
```

Expected JSON:

```json
{"final_amount":16288.95,"total_interest":6288.95}
```

## Test 3: Stock quote (happy path)

Requires `FINNHUB_API_KEY`.

```bash
curl -sS \
  -X POST "http://localhost:8000/tools/get_stock_quote" \
  -H "Content-Type: application/json" \
  -d '{"symbol":"AAPL"}'
```

Expected JSON shape (values vary with market):

```json
{
  "symbol": "AAPL",
  "price": 0.0,
  "currency": null,
  "as_of": "2025-03-19T20:00:00Z",
  "source": "Finnhub",
  "change": null,
  "percent_change": null
}
```

## Test 4: Stock quote without API key

Remove or empty `FINNHUB_API_KEY` in `.env` (or temporarily rename `.env`), restart the server, then:

```bash
curl -sS -i \
  -X POST "http://localhost:8000/tools/get_stock_quote" \
  -H "Content-Type: application/json" \
  -d '{"symbol":"AAPL"}'
```

Expected: **503** with detail that `FINNHUB_API_KEY` is not set (add it to `.env` or the environment).

## Test 5: Tool route rejects invalid input (FastAPI/Pydantic validation)

Example: missing field(s) should return **422**.

```bash
curl -sS -i \
  -X POST "http://localhost:8000/tools/calculate_compound_interest" \
  -H "Content-Type: application/json" \
  -d '{"principal":10000,"rate":0.05}'
```

Expected:

- Status contains `422 Unprocessable Entity`

## Test 6: Tool route rejects invalid domain values (ValueError)

The compound-interest tool raises `ValueError` for invalid domain inputs (`principal <= 0`, `rate < 0`, `years < 0`).

Example:

```bash
curl -sS -i \
  -X POST "http://localhost:8000/tools/calculate_compound_interest" \
  -H "Content-Type: application/json" \
  -d '{"principal":0,"rate":0.05,"years":10}'
```

Expected:

- A **500** response (current behavior) because FastAPI isn’t yet mapping `ValueError` to a 4xx.

If you want this to be a clean 400 later, add an exception handler for `ValueError`.

## Test 7: MCP tool discovery (end-to-end)

### Option A: Cursor / Claude Desktop (recommended)

1. Ensure the server is running (`python main.py`) with `FINNHUB_API_KEY` in `.env` if you want quotes.
2. Add the MCP server configuration (example uses `mcp-remote` as the bridge):

```json
{
  "mcpServers": {
    "mcp-finance-tools": {
      "command": "npx",
      "args": ["mcp-remote", "http://localhost:8001/mcp"]
    }
  }
}
```

3. In your MCP client UI, verify tools are discovered.

Expected tool names:

- `calculate_compound_interest`
- `get_stock_quote`

### Option B: Validate MCP endpoint behavior (basic)

The `/mcp` endpoint uses a streaming transport and won’t behave like a normal JSON REST endpoint in a browser/curl.

If you `curl http://localhost:8001/mcp` (or your chosen port) you may see an error like **406 Not Acceptable**. That’s expected unless you’re using an MCP client/transport.

## Test 8: Agent-style chain (manual)

Ask your agent something like:

> What’s AAPL at right now? If I put $10k in a 1-year CD at 4% annual interest, what’s approximate after-tax interest in Florida?

Expected behavior:

- **AAPL**: agent calls **`get_stock_quote`** (not a hallucinated price).
- **CD interest**: agent uses **`calculate_compound_interest`** or simple interest math as appropriate, and states **tax assumptions**. Florida has **no state income tax**; “after-tax” usually means **after federal tax** unless the user specifies a combined rate.
