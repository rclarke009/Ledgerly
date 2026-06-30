# Ledgerly — User instructions

This guide explains what to enter in each part of Ledgerly and where you can find that information. No financial jargon is assumed.

---

## What Ledgerly does

Ledgerly helps you keep track of **safe, income-earning assets** (like CDs and money-market accounts) and **upcoming bills or obligations**. You enter your accounts and holdings once; Ledgerly can then remind you when something is maturing or when a payment is due, and you can ask questions about your data and your uploaded documents.

---

## Quick glossary

| Term | Plain English |
|------|----------------|
| **Account** | A container at one bank or institution (e.g. “My savings at First National”). You create accounts first; then you add positions inside them. |
| **Position** | One specific holding inside an account—e.g. one CD, or one money-market fund. Each position has an amount (principal), a rate, and often a maturity date. |
| **Principal** | The amount of money in that holding (e.g. $10,000 in a CD). |
| **APR** | Annual Percentage Rate—the yearly interest rate (e.g. 4.5 means 4.5% per year). |
| **Maturity date** | The date when a CD or similar product “matures”—i.e. you can withdraw the money without penalty or renew it. |
| **Obligation** | Something you owe or must pay by a certain date (e.g. property tax, insurance premium, loan payment). |
| **Ingest** | Uploading or pasting document text into Ledgerly so you can search and ask questions about it later. |
| **Doc ID / Document ID** | An optional label you give to a document or link to a record (e.g. `statement-jan-2024`). Used to tie documents to accounts or positions. |

---

## Tab-by-tab guide

### Ingest

Use this to add **document text** (statements, letters, reports) so you can ask questions about it in the **Ask** tab.

| Field | What it means | Example | Where you find it |
|-------|----------------|--------|-------------------|
| **Text to ingest *** | The actual text from a document (when not uploading a PDF). | Paste the body of a bank letter, statement, or report. | Open the PDF or email, select all, copy, and paste. Or type a short note. Or use “PDF file” below to upload a PDF instead. |
| **Doc ID** (optional) | A short identifier for this document. | `cd-renewal-2024`, `statement-jan-2024` | You make this up—use something you’ll recognize later. |
| **Title** (optional) | A human-readable title. | `January 2024 bank statement` | You choose; often the document’s title or subject. |
| **Source** (optional) | Where the document came from. | `Bank of X – statement.pdf` | File name, email subject, or “website” etc. |
| **PDF file** (optional) | Upload a PDF instead of pasting text. | Choose a statement or letter PDF. | Use “PDF file” to upload; the same optional fields (Doc ID, Title, Source) apply. Text is extracted from the PDF and ingested like pasted text. |

You can either **paste text** (in “Text to ingest”) **or upload a PDF** (using “PDF file”)—**not both**. If you fill both and click Ingest, the app will ask you to clear one. If you upload a PDF, the same optional fields (Doc ID, Title, Source) apply; the PDF’s text is extracted and ingested like pasted text. Image-only or empty PDFs cannot be ingested (no text to extract).

\* Required when pasting text (omit when uploading a PDF).

---

### Ask

Use this to **ask questions** about your ingested documents and your accounts, positions, and obligations.

| Field | What it means | Example | Where you find it |
|-------|----------------|--------|-------------------|
| **Question *** | What you want to know. | `What’s my total in CDs?`, `When does my biggest CD mature?`, `Summarize the key points of my last statement.` | You type any question; Ledgerly uses your data and documents to answer. |
| **Limit to document** (optional) | Restrict the answer to one document. | Pick “January 2024 statement” from the list. | Dropdown is filled from documents you’ve ingested. Leave “All documents” to search everything. |
| **Top K chunks** | How many text snippets to use when answering. | Default 5 is usually enough. | Leave as 5 unless you want more or fewer sources. |

\* Required

---

### Data → Accounts

**Accounts** are your containers at each institution (e.g. one checking relationship, one brokerage). Create an account first; then add **positions** (individual CDs or funds) under it.

| Field | What it means | Example | Where you find it |
|-------|----------------|--------|-------------------|
| **Name *** | What you call this account. | `Emergency fund – First National`, `Brokerage savings` | You choose—often the account name on the bank or statement. |
| **Type** (optional) | Kind of account. | `Savings`, `Money market`, `Brokerage` | On your statement or online banking; use whatever label helps you. |
| **Institution** (optional) | Bank or company that holds the account. | `First National Bank`, `Vanguard` | On the statement header, card, or website. |
| **Document ID** (optional) | Link to an ingested document. | Choose from the dropdown or leave “(No document)”. | The dropdown lists all documents you’ve ingested; pick one to link, or leave as “(No document)”. |

\* Required

---

### Data → Positions

A **position** is one specific holding inside an account (e.g. one CD, one money-market fund). Each position belongs to one **account**.

| Field | What it means | Example | Where you find it |
|-------|----------------|--------|-------------------|
| **Account *** | Which account at your institution holds this holding. Create accounts under Data → Accounts first if needed. | Select “Emergency fund – First National” from the list. | You pick from the accounts you already created. |
| **Asset type *** | Type of product. | `CD`, `Money market`, `Treasury` | On the statement or certificate; common terms: CD, money market, savings, treasury. |
| **Description** (optional) | Short note about this holding. | `6‑month CD #1234`, `Primary MM fund` | You write this—helps you tell multiple positions apart. |
| **Principal** (optional) | Amount of money in this holding. | `10000`, `25000.50` | On the statement or CD certificate as “balance,” “principal,” or “amount.” Enter numbers only (no $ or commas). |
| **Rate APR** (optional) | Annual interest rate (%). | `4.5`, `5.25` | On the CD or account disclosure as “APR,” “interest rate,” or “yield.” Enter the number (e.g. 4.5 for 4.5%). |
| **Maturity date** (optional) | Date the CD or term ends (YYYY-MM-DD). | `2024-12-15` | On the CD certificate or statement as “maturity date” or “term end.” Use numbers: year-month-day. |
| **Document ID** (optional) | Link to an ingested document. | Choose from the dropdown or “(No document)”. | Shown when **creating** a position only; not shown when editing (multiple-document linking planned). |

\* Required

**Naming tips**

- **Account names** — Use a name that describes the relationship or purpose, e.g. *Emergency Spending – Fairwinds*, *Brokerage Core – Vanguard*, *CD Ladder – PenFed*.
- **Positions** — Use the specific instrument, e.g. *4.85% 12-mo CD maturing 2026-11*, *VMFXX Money Market*.

---

### Data → Obligations

**Obligations** are things you must pay by a certain date (bills, taxes, premiums, loan payments). Ledgerly can remind you when they’re due.

| Field | What it means | Example | Where you find it |
|-------|----------------|--------|-------------------|
| **Description *** | What the obligation is. | `Property tax – County`, `Car insurance renewal`, `Loan payment #12` | You write a short label so you recognize it. |
| **Due date *** | When it’s due (YYYY-MM-DD). | `2024-04-15`, `2024-06-01` | On the bill, reminder, or loan schedule. Use year-month-day. |
| **Amount estimate** (optional) | Approximate amount you’ll pay. | `1200`, `450.00` | On the bill or last statement; enter numbers only. |
| **Priority** (optional) | How important or urgent (for your own use). | `High`, `Must pay`, or leave blank | You decide; helps when reviewing advice. |
| **Document ID** (optional) | Link to an ingested document. | Choose from the dropdown or “(No document)”. | Shown when **creating** an obligation only; not shown when editing (multiple-document linking planned). |

\* Required

---

### Status (Decision status)

Click **Check status** to get **current advice** based on your accounts, positions, and obligations. Ledgerly looks for things like:

- CDs or similar products **maturing soon**
- **Obligations due** in the near future

You don’t fill in any fields here—just click the button. The result will say whether any action is suggested and show a short memo and sources (your data and any web links used).

---

### Past advice

This shows **history** of previous “Check status” runs—what the status was and when. Use it to see how your situation looked on earlier dates. Click **Load history**; no fields to fill.

---

### Documents (drawer)

Click **Documents** in the header to open a list of **ingested documents** (doc ID, title, source, chunk count). Use this to see what’s in the system and to pick a document when using **Limit to document** in the Ask tab. No data entry—just viewing.

---

## Example workflow

1. **Add an account** (Data → Accounts → Add account): e.g. Name “Savings – First National,” Institution “First National Bank.”
2. **Add a position** (Data → Positions → Add position): Choose that account, Asset type “CD,” Principal 10000, Rate APR 4.5, Maturity date 2024-12-15.
3. **Ingest a document** (Ingest): Paste text from a bank letter, set Doc ID `cd-letter-2024`, then submit.
4. **Ask** (Ask): e.g. “When does my CD at First National mature?” or “Summarize my CD letter.”
5. **Check status** (Status): Click “Check status” to see if any CDs are maturing or obligations are due.

---

## Date format

Whenever a date is requested (maturity date, due date), use **YYYY-MM-DD** (year, then month, then day). Examples: `2024-03-15`, `2025-01-01`. This avoids confusion between US (MM/DD) and other formats (DD/MM).

---

## Need more help?

- **Setup and running the app:** see `setup_and_testing.md`.
- **How the assistant works and privacy:** see `FINANCIAL-ASSISTANT.md` and `overview.md`.
