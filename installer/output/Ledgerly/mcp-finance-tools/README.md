# mcp-finance-tools

MCP server with **local financial calculation tools** (e.g. compound interest) and **optional market-data tools** that call [Finnhub](https://finnhub.io/) using your API key.

- **Calculations** run on your machine; inputs are not sent to a market vendor.
- **Quotes** (`get_stock_quote`) send the **symbol** to Finnhub over HTTPS. Put **`FINNHUB_API_KEY`** in a **`.env`** file in this directory (see `.env.example`); `python-dotenv` loads it when the server starts. Variables **already set in your shell** take precedence over `.env`.

## Run

```bash
cd mcp-finance-tools
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set FINNHUB_API_KEY=... (optional; required for stock quotes)
python main.py
```

- **Docker (Ledgerly `docker compose`)**: the finance service is exposed on the host as **http://localhost:8001** (container listens on 8000). MCP URL: **http://localhost:8001/mcp**.
- **Standalone `python main.py`**: default is **http://localhost:8000** — use **`PORT=8010`** (or any free port) if Ledgerly’s main app already uses 8000. MCP path is still **`/mcp`**.

## Spike: test Finnhub without the server

Uses the same **`mcp-finance-tools/.env`** as the server.

```bash
python scripts/spike_finnhub.py AAPL
```

## MCP client configuration

To connect an MCP client (e.g. Cursor, Claude Desktop), point it at the MCP URL. Example with `mcp-remote`:

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

Ensure the server is running before connecting.

## Agent behavior

For **current prices or market data**, agents should call the dedicated tools (e.g. `get_stock_quote`) and **must not guess** prices from internal knowledge. See repo `AGENTS.md` and `TESTING.md` for a sample multi-part question chain.
