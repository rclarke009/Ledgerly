# Decision status test guide

This guide explains how to test **Home status** and **decision memos** in Ledgerly. Status is either **No action required** or **Actionable**, based on positions, obligations, and IRA awareness dates in configured trigger windows (default: 30 days for maturities/obligations, 45 days for IRA).

## How it works

- **Home** loads automatically — there is no separate Status tab.
- **No action required**: No CD maturities, obligations, or IRA relevant dates in the trigger windows.
- **Actionable**: At least one trigger fired. Home shows **What to do** tips and fetches `GET /decision` for a structured memo (rate comparison, liquidity cross-check, optional OpenAI bullets).

Positions and obligations live under **Manage → Data**. Ingest can auto-track dates from documents; confirm or undo on Home.

Use **relative dates** (e.g. 14 days from today) so scenarios stay valid.

---

## Scenario A — No action required

1. **Manage → Data → Accounts**: Add an account (e.g. "Savings – First National").
2. **Manage → Data → Positions**: Add a CD with maturity **more than 30 days from today**.
3. Open **Home** (or click Refresh).
4. **Expected**: "All clear" / no action required memo.

---

## Scenario B — Actionable (maturity + decision memo)

1. Add a CD with maturity **within 30 days**.
2. Open **Home**.
3. **Expected**: "Action needed", renewal tips, and under **Decision memo**: rate comparison vs benchmarks, liquidity note, recommendation lines.
4. Optional: add an obligation due within ±14 days of maturity to test liquidity cross-check.

---

## Scenario C — Actionable (obligation)

1. **Manage → Data → Obligations**: Add a bill due **within 30 days**.
2. **Expected**: Actionable status with obligation tips.

---

## Scenario D — CD ladder table

1. Add several CD positions with staggered maturity dates.
2. **Expected**: **CD ladder** table on Home with institution, type, principal, APY, start, maturity, days until, next action.

---

## Scenario E — IRA awareness

1. **Manage → Data → IRA overview**: Add a row with **next relevant date** within 45 days.
2. **Expected**: IRA line on Home; actionable if date is in window. Ask preset **Next decision trigger** lists it.

---

## curl examples

Base URL: `http://localhost:8000`.

**Decision check:**

```bash
curl -s "http://localhost:8000/decision" | python3 -m json.tool
```

**Dashboard (includes ladder_positions):**

```bash
curl -s "http://localhost:8000/dashboard?days=365" | python3 -m json.tool
```

---

## Past advice

**Manage → Past advice → Load history** shows persisted memos from prior `GET /decision` runs.

---

## Real data pack (full walkthrough)

For copy-paste ingest text, saved-data tables, and Ask questions you can paste into the UI, see **[Real data pack (copy-paste)](../setup_and_testing.md#real-data-pack-copy-paste)** in [`setup_and_testing.md`](../setup_and_testing.md).
