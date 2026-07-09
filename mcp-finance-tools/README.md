# mcp-finance-tools

MCP server with **FRED Treasury safe-yield benchmarks** (CD/MMF proxies), **local financial calculations**, and **optional Finnhub stock quotes**.

- **Benchmarks** (`get_safe_yield_benchmarks`) call [FRED](https://fred.stlouisfed.org/) with public Treasury series IDs only — **no user PII** is sent.
- **Calculations** run on your machine; inputs are not sent to a market vendor.
- **Quotes** (`get_stock_quote`) send the **symbol** to Finnhub over HTTPS when `FINNHUB_API_KEY` is set.

## Run

```bash
cd mcp-finance-tools
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: FRED_API_KEY=... (live benchmarks), FINNHUB_API_KEY=... (optional quotes)
python main.py
```

- **Docker (Ledgerly `docker compose`)**: host **http://localhost:8001** → MCP **http://localhost:8001/mcp**.
- **Standalone**: default **http://localhost:8000** — use `PORT=8010` if Ledgerly UI uses 8000.

## MCP tools

| Tool | Egress | Purpose |
|------|--------|---------|
| `get_safe_yield_benchmarks` | FRED (optional) | Treasury proxies for 3/6/12/24-month CD terms + MMF |
| `compare_rate_delta` | None | Compare holding APY % vs benchmark APY % |
| `calculate_compound_interest` | None | Compound growth |
| `calculate_simple_interest` | None | CD-style simple interest |
| `get_stock_quote` | Finnhub (optional) | Stock/ETF price |

Without `FRED_API_KEY`, benchmarks return curated fallback tiers (same defaults as Ledgerly).

## Spike scripts

```bash
python scripts/spike_fred.py DGS1
python scripts/spike_finnhub.py AAPL
```

## MCP client configuration

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

See [CONNECTING.md](CONNECTING.md) and [TESTING.md](TESTING.md) for HTTP fallbacks and test plan.

## Privacy

FRED requests include only public series IDs (`DGS3MO`, `DGS6MO`, `DGS1`, `DGS2`) and your API key. Finnhub requests include only ticker symbols. User account data, document text, and questions never pass through this server.
