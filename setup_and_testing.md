# Ledgerly — Setup and Testing

## Prerequisites: Ollama (LLM and embeddings)

The app uses **Ollama** for both the LLM (answer generation) and embeddings. Default config expects:

- **LLM:** `qwen3:8b` at `http://localhost:11434`
- **Embeddings:** `nomic-embed-text` at the same base URL

### Start Ollama and pull models

```bash
# Start the Ollama server (if not already running as a service)
ollama serve
```

In another terminal, pull the models so the API can load them:

```bash
# LLM used by POST /ask (see app/config.py: LLM_MODEL)
ollama pull qwen3:8b

# Embedding model used for ingest and ask (EMBED_MODEL)
ollama pull nomic-embed-text

# Vision for POST /ask/image, POST /ingest/image, and PDF vision fallback (LLAVA_MODEL)
ollama pull llava:7b
```

Large PDF ingests use batched calls to Ollama (`EMBED_BATCH_SIZE`, default 32) with `EMBED_TIMEOUT` (default 120s) per batch—tune in `.env` if you still see timeouts or want smaller requests.

**Queued multi-file ingest:** Upload multiple PDFs/images in one go via **POST /ingest/jobs** (the Ingest UI uses this when you select more than one file). Jobs run **one at a time** in the background; tune `INGEST_QUEUE_INTER_JOB_SLEEP_SEC` and `EMBED_INTER_BATCH_SLEEP_SEC` in `.env`. Poll **GET /ingest/jobs** (the UI refreshes about every **60s** per `INGEST_UI_POLL_INTERVAL_SEC`). The in-memory queue does **not** survive a server restart.

### Vision, OCR, and memory (what users do vs what admins configure)

**Normal use (no special steps):** For scanned or screenshot PDFs, prefer **Auto** or **OCR** in the Ingest UI (`pdf_text_mode`). Auto tries embedded text first, then **Tesseract OCR** when the PDF looks image-like; for smaller PDFs it may fall back to the vision model per page (capped by `PDF_VISION_MAX_PAGES`). OCR avoids calling the vision model on every page, which is slower and harder on GPU RAM. You do **not** need to close apps or “free memory” for routine ingest.

**One-time setup:** Whoever installs Ledgerly should set **`LLAVA_MODEL`** in `.env` to a vision model that actually runs on this machine (default `llava:7b`; see `.env.example`). On a machine with plenty of RAM, you can switch to a larger model (e.g. `qwen2.5vl:7b`) after `ollama pull`. If Ollama still reports insufficient memory, use a **smaller** vision model from the Ollama library.

**Portable / low-spec profile:** Set **`LEDGERLY_PROFILE=portable`** or **`LEDGERLY_PROFILE=low_spec`** in `.env` and **omit `LLAVA_MODEL`** (or leave it commented) to use the built-in smaller default (`moondream`). Run `ollama pull moondream` once. If you explicitly set `LLAVA_MODEL`, that value always wins.

**Troubleshooting only (admins):** If ingest still fails with Ollama errors about **system memory** or **VRAM**, check that Tesseract OCR is installed so PDFs can use OCR instead of vision; confirm `ollama pull` succeeded for `LLAVA_MODEL`; try a smaller vision model; optionally check `ollama ps` to see which models are loaded. Reducing concurrent heavy GPU use is a last resort, not a daily user workflow.

Optional: run the LLM interactively (also pulls if needed):

```bash
ollama run qwen3:8b
```

---

## App setup

```bash
cd Ledgerly
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and adjust if needed (e.g. `DATABASE_PATH`, `LLM_BASE_URL`). Defaults work for local Ollama.

### Postgres + pgvector (Supabase or local)

Set `DATABASE_URL` to the Postgres URI (Project Settings → Database → Connection string; see `supabase_migration.md`). When set, the app uses **Postgres for all API data** and **pgvector** for `/ask` retrieval (no 5k embedding cap; index-backed `ORDER BY embedding <=> query`). Apply Supabase SQL migrations under `supabase/migrations/` in order (phase1 schema, financial tables, then `20250320000000_schema_parity_content_hash_tags.sql` for `content_hash` and `document_tags`). The HNSW index is created by migration / `ensure_postgres_schema`; on very large tables, building it can take time.

Leave `DATABASE_URL` unset to use **SQLite** at `DATABASE_PATH` (default `ledgerly.db` in config). If you have an old SQLite file from a prior install named `finelly.db`, rename it to `ledgerly.db` or set `DATABASE_PATH=finelly.db` in `.env`.

### Hosted Supabase logging (optional; separate from app database)

**App data** and **error telemetry** use different settings. You can keep documents/embeddings **local** (SQLite or local Postgres) while still sending **sanitized** server events to a **hosted** Supabase project for the dashboard.

| Purpose | Variable | Typical use |
|--------|-----------|-------------|
| Documents, chunks, embeddings, financial tables | `DATABASE_URL` | Unset → local SQLite; set → Postgres (local Supabase, Docker, or cloud). |
| Fire-and-forget error / slowdown logs (no PII) | `REMOTE_LOG_URL`, `REMOTE_LOG_SECRET`, optional `SUPABASE_ANON_KEY`, `REMOTE_LOG_INSTANCE_ID` | Point `REMOTE_LOG_URL` at your **hosted** Edge Function, e.g. `https://YOUR_PROJECT_REF.supabase.co/functions/v1/ingest-remote-log`. |

`REMOTE_LOG_URL` does **not** use `DATABASE_URL`. Deploy the Edge Function and apply the `remote_log_events` migration on the **hosted** project (see [`supabase/README.md`](supabase/README.md)). Use `REMOTE_LOG_INSTANCE_ID` (e.g. a UUID) to distinguish dev vs production instances in the same table.

Start the API:

```bash
uvicorn app.main:app --reload
```

Or use `./start-ledgerly.sh`, which also auto-sets `OLLAMA_NUM_THREADS` when unset (same conservative default as `start.sh`).

Default: `http://localhost:8000`. The same server serves the **web UI** at the root URL (see below).

---

## Run with Docker

The simplest way to run Ledgerly (no Python or Ollama installed on the host) is with Docker. **No .env or secrets are required** for the default setup.

Compose includes an internal **Postgres 16 + pgvector** service (not published on the host — only the app container can connect). The app sets `DATABASE_URL` to that database so `/ask` uses indexed vector search. Schema is created on first startup (`ensure_postgres_schema`). Data lives in the **`postgres_data`** Docker volume alongside Ollama and app volumes.

**Prerequisites:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed (Windows, Mac, or Linux).

### Main path: launcher script

1. Open a terminal in the Ledgerly project folder (the one that contains `docker-compose.yml`).
2. **Windows:** Double-click **`Start.bat`** or run `Start.bat` from a terminal. The script starts the containers, waits for Ollama, pulls the models (one-time), then opens http://localhost:8000/ in your browser.
3. **Mac/Linux:** Run `./start.sh`. Then open **http://localhost:8000/** in your browser.

`start.sh` auto-sets `OLLAMA_NUM_THREADS` from your CPU count when it is not already in `.env` (conservative default to reduce fan noise). Set `OLLAMA_NUM_THREADS` explicitly to override.

First run may take **much longer** than later runs (Docker images plus several gigabytes of Ollama models). **Later starts** are usually on the order of a few minutes once everything is cached; **daily use** after that is mostly startup time for containers, not re-downloads. For a plain-language table of what to expect (useful when handing the ZIP or installer to someone else), see **`install-instructions.md`** in the project root.

**To stop:** In the same folder run `docker compose down`. Data (Postgres, Ollama models, `/data` volume) is kept in Docker volumes.

### Alternative: manual Compose

```bash
# From the project root (folder that contains docker-compose.yml)
docker compose up -d
```

Then one-time, pull the models:

```bash
docker compose exec ollama ollama pull qwen3:8b
docker compose exec ollama ollama pull nomic-embed-text
docker compose exec ollama ollama pull llava:7b
```

Vision and OCR behavior (including when to use **OCR** vs vision for PDFs) is described under [Vision, OCR, and memory](#vision-ocr-and-memory-what-users-do-vs-what-admins-configure) above.

Open **http://localhost:8000/**.

### Optional: use your own .env

`docker-compose.yml` already uses `env_file: .env` for the `ledgerly` service. Variables in the `environment:` block **override** `.env` for those keys — notably **`DATABASE_URL`** is fixed to the internal Postgres URL so the portable/Docker path always uses pgvector. To point the container at a different database you’d need to edit compose (not typical for the zip install).

Do not commit real secrets to the repo.

---

## Web UI

After starting the API with `uvicorn app.main:app --reload`, open a browser at:

**http://localhost:8000/**

You get a single-page UI with **menu/tabs** so you can focus on one task at a time.

### Tabs

- **Ingest** — Paste or enter financial document text, or upload a PDF file; optionally set doc ID, title, and source. Submit to run ingest. Success or error message appears below the form. **PDF text mode** (PDF uploads only): *Auto* uses the PDF’s text layer when it looks complete; otherwise it tries **Tesseract OCR** (install the `tesseract` binary on the host; Docker image includes it) and, for smaller PDFs, may fall back to the **vision** model (LLM per page, capped—see `PDF_VISION_MAX_PAGES` in `.env.example`). For scans, **OCR** is usually the best first choice (no need to manage GPU memory). Choose *Text layer only* for normal text PDFs; *Vision* only if OCR is insufficient. Same `pdf_text_mode` field applies to **POST /ingest/pdf** and **POST /ingest/jobs** (queued multi-file). JPG/PNG still use **POST /ingest/image** (vision model), not these PDF modes.
- **Ask** — Enter a question (e.g. What does this document say about early withdrawal? or Summarize the fees and rates.). Optionally limit the search to one document (dropdown). Submit to get an answer and expandable “Source chunks.” The document dropdown is filled from the list of ingested documents and is refreshed after each ingest.

**Ollama preload:** Opening the **Ask** or **Add document** tab triggers a background warmup (`POST /warmup/ask` or `/warmup/ingest`) that loads the embedding model and the text LLM (Ask) or vision model (Ingest) into Ollama RAM. You may see a brief “Getting AI ready…” hint; the first real question or upload should be faster than a cold start. Disable with `OLLAMA_WARMUP_ENABLED=false` in `.env`. Tune `OLLAMA_WARMUP_KEEP_ALIVE` and `OLLAMA_WARMUP_SESSION_SEC` to control how long models stay loaded.

The last selected tab is remembered in the browser (localStorage) for the next visit.

### Document review (Documents tab)

Click **Documents** in the header to open the Document review tab. Click **Load documents** (or switch to the tab) to fetch and show ingested documents: title, snippet, chunk count, tags, and linked account. Each row has **Edit** (tags, source path, linked account via `PATCH /documents/{doc_id}`) and **Delete** (`DELETE /documents/{doc_id}`), which removes the document and any positions or obligations linked to it via `document_id`. Accounts are kept; only the document link on the account is cleared.

### Quick test flow

1. Open http://localhost:8000/.
2. Switch to the **Ingest** tab, paste some text (or upload a PDF), set a title and doc_id if you like, then submit.
3. Open the **Documents** tab and click **Load documents** to confirm the new doc appears; use **Edit** to set tags or linked account if you like.
4. Switch to the **Ask** tab, type a question that relates to the ingested text, then submit. Check the answer and “Source chunks.”

### Errors and Reference IDs

If the UI shows an error while **Ingest**, **Ask**, or **Saved data** is running (for example AI backend timeouts or connection issues), the red message often includes **Reference ID: …**. Give that exact ID to whoever runs Ledgerly; they can `grep` the ID in API logs (`request_id`) or centralized logs (e.g. Grafana/Loki) to find what failed. Responses also expose the same correlation ID in `X-Request-ID` HTTP headers where applicable.

---

## Final live tests (Ask tab)

Use this section **after** the app is running and you have done at least the [Quick test flow](#quick-test-flow) once. These are **real questions to type into the Ask tab** — not curl, not pytest. They complement the API steps in [`test_plan.md`](test_plan.md) and the Status-tab walkthrough in [`docs/decision-status-test-guide.md`](docs/decision-status-test-guide.md).

**How to run each test**

1. Open **http://localhost:8000/** → **Ask** tab.
2. Copy the question below into **Question** (edit dates or names only if your test data differs).
3. Optionally pick **Limit to document** when noted.
4. Submit and check:
   - **Answer** — sensible, grounded in your data or documents (not generic filler).
   - **Source chunks** — expand when you expect document retrieval; empty is OK for pure “saved data” fast paths.
   - **Errors** — none; if you see **Reference ID**, note it for logs.

**Suggested setup (pick one track or do both)**

| Track | What to prepare first |
|-------|------------------------|
| **Documents** | Ingest tab: paste the CD sample from [curl Ingest example](#ingest-post) below, or paste text from [`docs/sample-cd-maturity-letter.md`](docs/sample-cd-maturity-letter.md) / [`docs/sample-bill-reminder.md`](docs/sample-bill-reminder.md). |
| **Saved data** | **Data** tab: one account, one CD position (use a maturity date **within the next 90 days** for maturing-soon tests), and one obligation due **within the next 30 days** (e.g. property tax). |

---

### A — Document questions (RAG)

Run these after ingesting at least one financial document. Leave **Limit to document** on **All documents** unless noted.

| # | Type this question | What a good answer should do |
|---|-------------------|------------------------------|
| A1 | `What does this document say about early withdrawal?` | Mention penalty terms (e.g. 90 days interest) if you ingested the CD terms sample; cite source chunks from that doc. |
| A2 | `Summarize the fees and rates mentioned.` | Pull APY/rates and any fees from ingested text; source chunks should match. |
| A3 | `What is the maturity date on this CD?` | State the date from the letter or terms doc (e.g. March 15, 2026 or the date in your sample). |
| A4 | `What are my options at maturity?` | List renew / transfer / withdraw (or equivalent) from a maturity notice. |
| A5 | `When is the property tax due and how much?` | Use after ingesting [`docs/sample-bill-reminder.md`](docs/sample-bill-reminder.md): due date and amount from the notice. |
| A6 | `How can I pay this bill?` | Mail, online, or in-person options from the bill sample. |

**Document-scoped (optional):** Repeat **A1** or **A2** with **Limit to document** set to your ingested title — answer should stay on that file and chunks should all be from that `doc_id`.

---

### B — Saved data questions (accounts, CDs, obligations)

Run these after entering data in **Data → Accounts**, **Positions**, and **Obligations**. No ingest required for these to be meaningful.

| # | Type this question | What a good answer should do |
|---|-------------------|------------------------------|
| B1 | `How much do I have in CDs?` | Total and per-CD breakdown from your positions (fast path — answer is structured, often without source chunks). |
| B2 | `What's maturing in the next 3 months?` | List CDs/positions with maturity in the next 90 days; “none” if you only added far-future dates. |
| B3 | `What bills or obligations are due soon?` | Obligations due within the configured window (default 30 days). |
| B4 | `Summarize my accounts and holdings.` | Account names plus positions under each. |
| B5 | `When does my biggest CD mature?` | Uses saved positions (may combine with LLM); should name the CD and date you entered. |
| B6 | `What is my mortgage payment and when is it due?` | Only if you added an obligation whose description includes **mortgage** (e.g. “Home mortgage — First National”). |

---

### C — Combined documents + saved data

Prepare **both** tracks above, then try:

| # | Type this question | What a good answer should do |
|---|-------------------|------------------------------|
| C1 | `I got a maturity notice — what should I do before my CD matures?` | Blend letter options (renew/transfer/withdraw) with your tracked maturity date if positions match. |
| C2 | `Do I have any bills due soon that match documents I've uploaded?` | Compare obligations in Data with ingested bill/tax notices when dates align. |
| C3 | `Find my CD maturity letter and tell me the APR.` | Document search + rate from ingested maturity letter. |

---

### D — Sanity checks (should fail gracefully)

| # | Type this question | What a good answer should do |
|---|-------------------|------------------------------|
| D1 | `What is the weather in Paris tomorrow?` | No relevant context — expect a short “don't have relevant context or data” style message and **empty** source chunks (with a fresh/empty database). |
| D2 | `Summarize the fees and rates mentioned.` | With **no documents ingested** and no rate data in positions, expect no-context or a clear “nothing to summarize” outcome. |

---

### E — Other tabs (quick UI smoke tests)

Not Ask questions, but useful in the same “final check” session:

1. **Status** → **Check status** — “No action required” vs “Actionable” per [`docs/decision-status-test-guide.md`](docs/decision-status-test-guide.md).
2. **Documents** → **Load documents** — ingested titles appear; **Edit** tags; **Delete** removes a test doc you no longer need.
3. **Ingest** → upload a small PDF or paste text again — success message, then document shows up in Ask’s document dropdown.

---

### Pass criteria (short checklist)

- [ ] At least one **document** question (A1–A6) returns an answer grounded in ingested text with matching **Source chunks**.
- [ ] At least one **saved data** question (B1–B4) returns structured totals or lists without inventing accounts you never entered.
- [ ] One **combined** question (C1–C3) is reasonable when both docs and Data are populated.
- [ ] **D1** does not hallucinate weather or fake holdings on an empty or irrelevant question.
- [ ] No unexplained errors; any **Reference ID** is captured if something fails.

For deeper API/log debugging on the same questions, use [`test_plan.md`](test_plan.md) with the same wording in `POST /ask` and grep `X-Request-ID` in logs.

---

## curl commands

Base URL assumed: `http://localhost:8000`. Use `-s` for quieter output.

### Health check

```bash
curl -s "http://localhost:8000/health"
```

### List documents (GET)

Returns ingested documents (doc_id, title, source, created_at, num_chunks, snippet, tags, linked_account_ids). Same data used by the Web UI Documents tab.

```bash
curl -s "http://localhost:8000/documents"
```

### Update document (PATCH)

Update a document’s tags and/or linked account. Send only the fields you want to change. Use `account_id: null` to unlink all accounts from the document.

```bash
curl -s -X PATCH "http://localhost:8000/documents/cd-terms-2025" \
  -H "Content-Type: application/json" \
  -d '{"tags": ["2025", "CD"], "account_id": "some-account-uuid"}'
```

### Ingest (POST)

Requires a JSON body with at least `text`. Optional: `doc_id`, `title`, `source`, `chunking_options`.

```bash
curl -s -X POST "http://localhost:8000/ingest" \
  -H "Content-Type: application/json" \
  -d '{"text": "Certificate of Deposit terms: 12-month CD, 4.25% APY, $10,000 minimum. Early withdrawal incurs a penalty of 90 days interest. Maturity date: March 15, 2026.", "title": "CD terms 2025", "doc_id": "cd-terms-2025"}'
```

Minimal (server generates `doc_id`):

```bash
curl -s -X POST "http://localhost:8000/ingest" \
  -H "Content-Type: application/json" \
  -d '{"text": "Short document to ingest."}'
```

### Ingest PDF (POST /ingest/pdf)

Multipart: required `file` (PDF). Optional: `doc_id`, `title`, `source`, `chunk_size`, `chunk_overlap`, `tags`, `account_id`, `confirm_duplicate_content`, and **`pdf_text_mode`**: `auto` (default), `native` (embedded text only—fails on image-only PDFs), `ocr` (Tesseract on rendered pages), `vision` (LLM per page; max pages from `PDF_VISION_MAX_PAGES`). Large scanned PDFs in `auto` use OCR only (no vision fallback). Requires `pypdf`; OCR additionally needs `pymupdf`, `pytesseract`, `Pillow`, and the **tesseract** system binary.

```bash
curl -s -X POST "http://localhost:8000/ingest/pdf" \
  -F "file=@scan.pdf" \
  -F "pdf_text_mode=ocr" \
  -F "title=Scanned statement"
```

### Ingest image (POST /ingest/image)

Accepts JPG or PNG (e.g. bank screenshots). Uses LLaVA (Ollama) to extract all visible text, then runs the same chunk/embed pipeline as text and PDF. Requires LLaVA to be available (same as `/ask/image`). Multipart form: required `file`; optional `doc_id`, `title`, `source`, `chunk_size`, `chunk_overlap`, `tags`, `confirm_duplicate_content`. Max size 10 MB.

```bash
curl -s -X POST "http://localhost:8000/ingest/image" \
  -F "file=@screenshot.jpg" \
  -F "title=Bank statement screenshot" \
  -F "source=upload"
```

### Ask (POST)

Requires a JSON body with `question`. Optional: `top_k`, `doc_id`, `use_rag`.

After ingesting financial documents (e.g. statements, CD terms, or fee schedules), these questions verify RAG:

```bash
# Answerable from ingested docs: e.g. CD terms or statement
curl -s -X POST "http://localhost:8000/ask" \
  -H "Content-Type: application/json" \
  -d '{"question": "What does this document say about early withdrawal?"}'
```

```bash
# Answerable from ingested docs: fees, rates, or terms
curl -s -X POST "http://localhost:8000/ask" \
  -H "Content-Type: application/json" \
  -d '{"question": "Summarize the fees and rates mentioned."}'
```

With options (e.g. restrict to one document):

```bash
curl -s -X POST "http://localhost:8000/ask" \
  -H "Content-Type: application/json" \
  -d '{"question": "What does this document say about early withdrawal?", "top_k": 5, "doc_id": "cd-terms-2025"}'
```

**Note:** `GET /ask?question=...` is not supported; the endpoint expects **POST** with a JSON body.

### Ask image (POST /ask/image) — LLaVA vision

**POST /ask/image** sends an image to the vision model (Ollama) and returns descriptive text. No RAG. Requires `ollama pull` for whatever you set as `LLAVA_MODEL` (default `llava:7b`); uses the same `LLM_BASE_URL` as the text LLM. If Ollama runs out of memory, fix **`LLAVA_MODEL`** / install a smaller vision model—see [Vision, OCR, and memory](#vision-ocr-and-memory-what-users-do-vs-what-admins-configure).

**Option 1: JSON body** — provide a URL to an image and an optional prompt:

```bash
curl -s -X POST "http://localhost:8000/ask/image" \
  -H "Content-Type: application/json" \
  -d '{"image_url": "https://example.com/photo.jpg", "prompt": "Describe what you see and summarize any financial details or terms."}'
```

**Option 2: multipart/form-data** — upload an image file and optional prompt:

```bash
curl -s -X POST "http://localhost:8000/ask/image" \
  -F "image=@/path/to/your/image.jpg" \
  -F "prompt=Describe this image and summarize any financial details or terms."
```

Response: `{"answer": "..."}` (text from LLaVA). Image size limit: 10 MB.

---

## Google Drive ingest (read-only)

You can ingest **Google Docs** from Drive by authorizing once with OAuth, then calling **POST /ingest/google-drive**. The app only requests read-only access (`drive.readonly`).

### 1. Google Cloud project and OAuth client

1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a project (or pick an existing one) and enable **Google Drive API** (APIs & Services → Library → search “Google Drive API” → Enable).
3. Create OAuth credentials: **APIs & Services → Credentials → Create Credentials → OAuth client ID**.
4. If prompted, configure the **OAuth consent screen** (e.g. External, add your email as test user).
5. For **Application type** choose **Web application**.
6. Under **Authorized redirect URIs** add:  
   `http://localhost:8000/auth/google/callback`  
   (or the same URL with your host/port if you run the app elsewhere).
7. Copy the **Client ID** and **Client secret**.

### 2. Set env and run one-time OAuth

In your `.env` (or environment), set:

```bash
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
```

Optional: if the app is not on port 8000, set the callback URL to match what you registered:

```bash
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback
```

Start the app (`uvicorn app.main:app --reload`), then in a browser open:

**http://localhost:8000/auth/google**

Sign in with the Google account that has access to the Drive files you want to ingest. After you approve, you are redirected to a page that shows a line like:

```bash
GOOGLE_REFRESH_TOKEN="1//0abc..."
```

Add that line to your `.env` (or set the env var), then restart the app.

### 3. Ingest from Drive

**POST /ingest/google-drive** lists and exports Google Docs, then ingests them (chunk + embed + store). Request body (all optional):

- **folder_id** — only list files in this Drive folder.
- **file_ids** — only these file IDs (Google Doc IDs). If set, `folder_id` is ignored.

If both are omitted, the app lists Google Docs from the root of the authenticated user’s Drive.

Example (ingest all Docs in a folder):

```bash
curl -s -X POST "http://localhost:8000/ingest/google-drive" \
  -H "Content-Type: application/json" \
  -d '{"folder_id": "YOUR_DRIVE_FOLDER_ID"}'
```

Example (ingest specific Docs by ID):

```bash
curl -s -X POST "http://localhost:8000/ingest/google-drive" \
  -H "Content-Type: application/json" \
  -d '{"file_ids": ["id1", "id2"]}'
```

Response shape: `{"ingested": N, "skipped": M, "errors": [...], "doc_ids": [...]}`. Duplicate `doc_id` (same file already ingested) is counted as skipped; other failures are listed in `errors`.
