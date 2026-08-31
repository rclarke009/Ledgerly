# Ledgerly example kit

Fictional PDFs you can drop onto **Add document** so you can see how the app works without using your own statements.

These are **not** real bank or tax documents. Names and amounts are made up.

**Dates in the PDFs** are set so that around **late August / September 2026** Home should show **Action needed** (CD matures **September 18, 2026**; tax due **September 25, 2026**). If you open this kit much later, Home may show overdue items instead of “coming due.” You can still ingest and Ask about the documents.

---

## Files

| File | What it is |
|------|------------|
| `penfed-cd-maturity-notice.pdf` | A CD is about to mature; options to renew, move to money market, or withdraw |
| `county-property-tax-notice.pdf` | A property-tax installment with amount and due date |

---

## Scenario 1 — “I got a letter from the bank”

**Goal:** Ingest one PDF, let Ledgerly offer to track the CD, then ask questions about the letter.

1. Open Ledgerly → **Add document**.
2. Drop `penfed-cd-maturity-notice.pdf` (or click the drop zone and pick it).
3. Click **Ingest**. Wait until **Processing** shows success.
4. If a dialog asks **Yes, track this**, tap **Yes**.
5. Open **Home**. You should see a CD rung around **$25,000**, APY **4.85%**, maturity **September 18, 2026**.
6. Open **Ask** and try:

```
What is the maturity date on this CD?
```

```
What are my options at maturity?
```

```
What does this document say about early withdrawal?
```

A good answer cites the letter (renew / transfer / withdraw; 90 days of interest if you cash out early).

---

## Scenario 2 — “A bill is due right after my CD matures”

**Goal:** Two documents plus Ask about cash for the tax bill. This is the main “why would I use this?” story.

1. Ingest **both** PDFs (you can select both, then **Ingest**). Track the CD if prompted; track the tax bill if prompted.
2. Open **Home** → **Refresh** if the page was already open. You should see the CD **and** a **$1,200** obligation due **September 25, 2026**.
3. In **Ask**, try:

```
Do I need the September 18 CD rung to stay liquid for my property tax on September 25?
```

```
When is the property tax due and how much?
```

```
How can I pay this bill?
```

Expect: the **$25,000** maturity more than covers **$1,200** tax; due date and pay-by-mail / online / in-person from the notice.

**Optional:** **Manage → Data → Positions** and add a second rung so the ladder looks like a real household (you do not need a PDF for this):

| Account (create if needed) | Asset type | Description | Principal | APR | Maturity |
|----------------------------|------------|-------------|-----------|-----|----------|
| CD Ladder - PenFed | CD | 6-mo rung | 10000 | 4.60 | 2026-12-01 |

Then ask: `What's maturing in the next 3 months?`

---

## If something does not match

- **No “track this” dialog:** open **Manage → Data** and add the position / obligation by hand using the numbers in the PDFs.
- **Ask says it has no context:** wait until ingest finishes, then ask again. Use **Limit to document** and pick the PDF title.
- **Home says All clear:** the sample dates may be outside the 30-day window for your “today.” You can still use **Ask** on the ingested text.

Regenerate the PDFs after editing `generate_pdfs.py`:

```bash
python3 example-kit/generate_pdfs.py
```
