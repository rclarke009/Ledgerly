# Ledgerly — Private CD Ladder & Cash Management Assistant

Ledgerly is a **private cash-management assistant** focused on taxable CD ladders, safe cash alternatives (money market), known cash obligations, and IRA awareness. It is **not** a general investment or portfolio agent.

## Principles

- **Database is the source of truth** — Structured tables (`accounts`, `positions`, `obligations`, `ira_overview`) are authoritative; documents verify but do not override holdings.
- **Table-driven decisions** — Decisions come from your operating tables, not document-by-document analysis.
- **Trigger-based reasoning** — Recommendations only when a trigger fires (CD maturity, obligation due, IRA relevant date); otherwise **No action required**.
- **Source hierarchy** — (1) Your SoT tables, (2) uploaded documents, (3) generic public rate benchmarks, (4) general explanation. Public benchmarks never override your actual holdings.
- **Action threshold** — Do not recommend switching unless: material yield advantage, liquidity need, simplicity gain, known obligation, or imminent maturity.
- **Privacy first** — Documents stay local; OpenAI (optional) receives sanitized prompts only (amounts/rates, no names).

## Version 1 scope

### Do

- Maintain **CD ladder** positions (institution, type, principal, APY, start/maturity, next action, liquidity note)
- Track **obligations** and cross-check maturing principal vs nearby bills
- **IRA overview** rows for awareness (RMD dates, notes — not investment advice)
- **Home** status, ladder table, trigger alerts (default 30-day window; IRA 45-day)
- **Decision memos** at maturity: options (hold/roll/MMF/wait), rate comparison vs benchmarks, confidence footer
- Ingest PDFs/images; extract and confirm positions/obligations
- **Ask** presets including “What is my next decision trigger?”

### Do not

- Stock screening, active trading, portfolio optimization, macro commentary
- Autonomous “always-on” coaching or churn recommendations
- Tax or legal advice (awareness only)

## Operating tables

| Table | Purpose |
|-------|---------|
| `accounts` + `positions` | Taxable CD ladder and safe-income holdings |
| `obligations` | Known cash needs |
| `ira_overview` | IRA awareness (optional) |

## Output modes

1. **Status check** — Home dashboard: ladder, next dates, liquidity totals, no-action vs actionable
2. **Decision memo** — `GET /decision`: operational memo, rate comparisons, liquidity cross-check, optional OpenAI bullets
3. **Document extraction** — Ingest → structured extract → confirm/auto-track

## API (cash-focused)

| Endpoint | Purpose |
|----------|---------|
| `GET /dashboard` | Home snapshot incl. `ladder_positions`, `ira_overview` |
| `GET /decision` | Trigger engine + structured memo |
| `GET /decision/history` | Past advice log |
| `GET/POST/PATCH/DELETE /accounts`, `/positions`, `/obligations` | SoT CRUD |
| `GET/POST/PATCH/DELETE /ira-overview` | IRA awareness CRUD |
| `POST /ask` | RAG + fast paths over data and documents |

## Configuration

| Variable | Default | Notes |
|----------|---------|-------|
| `MATURITY_DAYS_AHEAD` | 30 | CD maturity trigger window |
| `OBLIGATION_DAYS_AHEAD` | 30 | Bill due trigger window |
| `IRA_DAYS_AHEAD` | 45 | IRA awareness trigger window |
| `LIQUIDITY_CROSSCHECK_DAYS` | 14 | ±days for obligation vs maturity cross-check |
| `REFERENCE_CD_RATES` | (empty) | Optional JSON benchmark overrides |
| `REFERENCE_MMF_APR` | 4.50 | MMF benchmark for comparisons |

## Run

```bash
cd <project-root> && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open the UI at http://localhost:8000 — **Home** for status and ladder; **Manage → Data** for tables; **Ask** for decision-framed questions.
