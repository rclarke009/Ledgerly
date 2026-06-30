# Connecting from an agent outside this project

This document explains how to connect to `mcp-finance-tools` from an external agent/client.

## What this server exposes

When running locally, the server exposes (replace host/port if you changed `PORT` or Docker mapping):

- **Docker Compose (Ledgerly)**: host **8001** → container 8000 — **MCP**: `http://localhost:8001/mcp`
- **Bare `python main.py`**: often **`http://localhost:8000`** unless you set `PORT` to avoid clashing with Ledgerly’s UI on 8000.
- **Tool HTTP routes (non-MCP fallback)**:
  - `POST .../tools/calculate_compound_interest`
  - `POST .../tools/get_stock_quote` (requires `FINNHUB_API_KEY`)

MCP tool names:

- `calculate_compound_interest`
- `get_stock_quote`

Set **`FINNHUB_API_KEY`** in **`mcp-finance-tools/.env`** (see `.env.example`; loaded by `python-dotenv` on startup) for stock quotes. Symbols are sent to Finnhub. Calculation tools run locally.

**Agent rule:** for current prices or market data, use **`get_stock_quote`** (or other market tools you add). **Do not guess** prices from internal knowledge.

## 1) Run the MCP server

```bash
cd mcp-finance-tools
source .venv/bin/activate
cp .env.example .env
# Edit .env: FINNHUB_API_KEY=... (optional; required for quotes)
python main.py
```

## 2) Connect using an MCP client (recommended)

Many MCP clients support “stdio servers” (a command they spawn) more reliably than direct HTTP MCP.
`mcp-remote` bridges **remote HTTP MCP** (`/mcp`) into a **local stdio MCP server**.

### Example config (Claude Desktop / Cursor-style)

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

Notes:

- This requires Node/npm because it uses `npx`.
- Start the FastAPI server first (`python main.py`), then start/reload your MCP client.

### How to use the tools once connected

**Compound interest**

- Tool: `calculate_compound_interest`
- Args:
  - `principal` (float)
  - `rate` (float as decimal, e.g. `0.05`)
  - `years` (int)

Example arguments:

```json
{"principal":10000,"rate":0.05,"years":10}
```

Expected result:

```json
{"final_amount":16288.95,"total_interest":6288.95}
```

**Stock quote (Finnhub)**

- Tool: `get_stock_quote`
- Args:
  - `symbol` (string, e.g. `AAPL`)

Example arguments:

```json
{"symbol":"AAPL"}
```

Expected result (shape; numbers vary):

```json
{
  "symbol": "AAPL",
  "price": 180.12,
  "currency": null,
  "as_of": "2025-03-19T20:00:00Z",
  "source": "Finnhub",
  "change": 1.23,
  "percent_change": 0.69
}
```

## 3) If your agent can’t speak MCP yet: call the HTTP routes directly

You can still use this project as a normal JSON API.

### cURL (compound interest)

```bash
curl -sS \
  -X POST "http://localhost:8001/tools/calculate_compound_interest" \
  -H "Content-Type: application/json" \
  -d '{"principal":10000,"rate":0.05,"years":10}'
```

### cURL (stock quote)

```bash
curl -sS \
  -X POST "http://localhost:8001/tools/get_stock_quote" \
  -H "Content-Type: application/json" \
  -d '{"symbol":"AAPL"}'
```

### Python (requests)

```python
import requests

base = "http://localhost:8001"  # Docker host port for finance-mcp
r = requests.post(
    f"{base}/tools/calculate_compound_interest",
    json={"principal": 10000, "rate": 0.05, "years": 10},
    timeout=10,
)
r.raise_for_status()
print(r.json())

q = requests.post(
    f"{base}/tools/get_stock_quote",
    json={"symbol": "AAPL"},
    timeout=15,
)
q.raise_for_status()
print(q.json())
```

## Example agent prompt chain

Ask:

> What’s AAPL at right now? If I put $10k in a 1-year CD at 4% annual interest, what’s approximate after-tax interest in Florida?

Expected:

- Call **`get_stock_quote`** for AAPL.
- For the CD, use **`calculate_compound_interest`** or simple interest; state that **Florida has no state income tax** and that **after-tax** needs a **federal marginal rate assumption** unless the user provides one.

## Troubleshooting

- **Port in use**: set `PORT` before running.

```bash
export PORT=8010
python main.py
```

- **`curl http://localhost:8001/mcp` returns 406**: expected; `/mcp` is not a normal REST endpoint. Use an MCP client or `mcp-remote`.

- **503 on `get_stock_quote`**: set `FINNHUB_API_KEY` in `.env` (or export it) and restart the server.
