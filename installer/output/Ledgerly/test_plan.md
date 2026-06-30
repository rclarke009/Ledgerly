# Ask API — manual test plan

This document walks step-by-step through calling the Ledgerly **Ask** HTTP endpoints, interpreting responses, and correlating requests with **`ask_trace`** instrumentation in server logs.

**Assumptions:** the API is running (e.g. `uvicorn` or Docker Compose). Examples use `http://localhost:8000` — replace with your base URL.

---

## Step 1 — Confirm the server is up

1. Open a terminal.
2. Run:

   ```bash
   curl -sS 'http://localhost:8000/health'
   ```

3. **Expect:** JSON like `{"healthy": true}`.

If this fails, start the app stack first (see `docker-compose.yml`, `start.sh`, or your usual dev command).

---

## Step 2 — Understand shared conventions

All Ask JSON endpoints use **`POST`** with **`Content-Type: application/json`** unless noted otherwise.

**Correlation with logs:**

- Every response includes header **`X-Request-ID`** (a UUID).
- Server log lines that look like: `ask_trace {"stage": "...", "request_id": "<same-uuid>", ...}` belong to that request (default format: prefix `ask_trace` + JSON).
- With **`LOG_JSON=true`**, each ask-trace line is **only** JSON (no `ask_trace` prefix), which is easier for **Grafana Loki** (`| json`) and log pipelines.
- To debug one question end-to-end: copy `X-Request-ID`, then grep logs for that id or for `ask_trace`.

**Example (capture request id):**

```bash
curl -sS -D - -o /tmp/ask_body.json -X POST 'http://localhost:8000/ask' \
  -H 'Content-Type: application/json' \
  -d '{"question":"What documents mention interest rates?","top_k":5}' \
  | head -20
```

Inspect the response headers for `X-Request-ID`, then inspect `/tmp/ask_body.json` for the JSON body.

---

## Step 3 — `POST /ask` (RAG, single JSON response)

**Purpose:** Run the full RAG pipeline (routing, optional finance tools, embed, retrieve, optional rerank, prompt build, local LLM) and return one JSON object.

**Request body fields** (`AskRequest`):

| Field       | Required | Default | Notes |
|------------|----------|---------|--------|
| `question` | yes      | —       | User question |
| `top_k`    | no       | `5`     | Max chunks after retrieval / rerank |
| `doc_id`   | no       | null    | Search only this document |
| `doc_ids`  | no       | null    | Search only these document ids |
| `tag`      | no       | null    | Search only documents with this tag |
| `use_rag`  | no       | `true`  | If `false`, skips document retrieval path |

**Steps:**

1. Ensure you have ingested at least one document if you expect RAG answers (or use `use_rag: false` / data-only scenarios).

2. Run:

   ```bash
   curl -sS -X POST 'http://localhost:8000/ask' \
     -H 'Content-Type: application/json' \
     -d '{"question":"What is my CD maturity date?","top_k":5}'
   ```

3. **Expect:** JSON with:
   - `answer` — markdown (and possibly structured tail parsed into `tables` / `charts`).
   - `top_chunks` — list of `{ chunk_id, doc_id, score, content_snippet }`.

4. **Optional — narrow scope:**

   ```bash
   curl -sS -X POST 'http://localhost:8000/ask' \
     -H 'Content-Type: application/json' \
     -d '{"question":"Summarize this file.","doc_id":"YOUR_DOC_ID","top_k":3}'
   ```

5. **If you see:** a fixed message like *“I don't have relevant context or data to answer that question.”* and empty `top_chunks`, check logs for `stage: "ask_early_exit"` and `reason: "no_context"`, and earlier stages (`retrieve`, `retrieval_gate`, `build_prompt`) to see why nothing was assembled into the prompt.

---

## Step 4 — `POST /ask/stream` (RAG, NDJSON stream)

**Purpose:** Same pipeline as `/ask`, but the model output streams as **newline-delimited JSON** (NDJSON).

**Request body:** Same as `/ask`.

**Steps:**

1. Run with **no buffering** (important for curl):

   ```bash
   curl -sS -N -X POST 'http://localhost:8000/ask/stream' \
     -H 'Content-Type: application/json' \
     -d '{"question":"Summarize my largest obligation."}'
   ```

2. **Expect — typical line sequence:**
   - First line: JSON object containing **`top_chunks`** (and serialized chunk metadata).
   - Many lines: `{"delta": "<text fragment>"}`.
   - Then: `{"structured": {"answer": "...", "tables": [...], "charts": [...]}}`.
   - Finally: `{"done": true}`.

3. **Early exit (no context):** you may get a **single** composite line that includes the no-context answer and `done` — still valid NDJSON for that path.

4. **Correlation:** `X-Request-ID` is on the **HTTP response** to this POST; the stream body does not repeat it. Save the id from headers if you need to grep `ask_trace` lines. Note: the streaming LLM phase runs **after** the graph build; logs for `llm_completion` with `kind: "stream"` should still share the same `request_id` when trace scope is active.

---

## Step 5 — `POST /ask/general` (OpenAI only, no documents)

**Purpose:** Templated or custom **general** finance Q&A via **OpenAI** — **no** RAG, **no** user documents.

**Prerequisite:** `OPENAI_API_KEY` must be set on the server. Otherwise expect **503** with a message that OpenAI is not configured.

**Request body** (`AskGeneralRequest`):

| `template`           | `question` | `amount` / `term_months` |
|----------------------|------------|---------------------------|
| `cd_rates_summary`   | omit       | omit |
| `cd_advice`          | omit       | optional — CD amount / term |
| `custom`             | **required** (non-empty) | omit |

**Steps:**

1. **Custom question:**

   ```bash
   curl -sS -X POST 'http://localhost:8000/ask/general' \
     -H 'Content-Type: application/json' \
     -d '{"template":"custom","question":"What is a Treasury bill in one paragraph?"}'
   ```

2. **CD environment summary:**

   ```bash
   curl -sS -X POST 'http://localhost:8000/ask/general' \
     -H 'Content-Type: application/json' \
     -d '{"template":"cd_rates_summary"}'
   ```

3. **CD advice with amount / term:**

   ```bash
   curl -sS -X POST 'http://localhost:8000/ask/general' \
     -H 'Content-Type: application/json' \
     -d '{"template":"cd_advice","amount":50000,"term_months":12}'
   ```

4. **Expect:** JSON with `answer`, and optionally `tables` / `charts` from structured parsing.

5. **Logs:** look for `stage: "ask_general_begin"` and `stage: "llm_completion"` with `kind: "openai_chat"` when tracing is enabled.

---

## Step 6 — `POST /ask/image` (vision, no RAG)

**Purpose:** Send an image to the **vision** model (e.g. LLaVA via Ollama) and get descriptive text — **not** RAG.

**Two ways to call:**

**A) JSON with URL**

```bash
curl -sS -X POST 'http://localhost:8000/ask/image' \
  -H 'Content-Type: application/json' \
  -d '{"image_url":"https://example.com/slip.png","prompt":"Extract balances and dates."}'
```

**B) Multipart file upload**

```bash
curl -sS -X POST 'http://localhost:8000/ask/image' \
  -F 'image=@/path/to/screenshot.png' \
  -F 'prompt=Summarize any financial numbers.'
```

**Expect:** JSON `{"answer": "..."}`.

This path does **not** use the same LangGraph ask trace sequence as `/ask`; correlation is still via normal request logs and `X-Request-ID`.

---

## Step 7 — Tie a manual test to `ask_trace` logs (checklist)

Use this after any `/ask`, `/ask/stream`, or `/ask/general` call when debugging.

1. **Note** `X-Request-ID` from the response headers.
2. **Tail** application logs (examples):
   - Docker: `docker compose logs -f ledgerly`
   - Local: the terminal running `uvicorn`
3. **Grep** for that UUID or for `ask_trace`:

   ```bash
   docker compose logs ledgerly 2>&1 | rg 'ask_trace|YOUR-REQUEST-ID-HERE'
   ```

4. **Walk stages in order** (typical RAG request):
   - `ask_begin` — filters, `top_k`, `use_rag`, question length
   - `classify_route` — `graph_route` (`data_only` / `docs_only` / `both`)
   - `finance_tools` — optional tool block
   - `embed_query` — embedding timing
   - `embed_batch` — cache hits/misses (under active trace)
   - `retrieval_db` — DB/backend timing and row counts
   - `retrieve` — attempt, broaden, scores pre/post rerank
   - `rerank` / `rerank_chunk` (DEBUG) — reranker detail
   - `retrieval_gate` — retry vs done and **reason**
   - `build_prompt` — `has_context`, lengths
   - `llm_completion` — chat vs stream vs openai; duration; **no** raw prompt in logs
   - `ask_early_exit` — only if no context was assembled

5. **Interpret “no answer”:**
   - Fixed sentence + empty chunks → `ask_early_exit` + `build_prompt` with `has_context: false`
   - HTTP 4xx/5xx → see status and app error handlers; optional `remote_log_events` if configured

---

## Step 8 — Observability stack (Prometheus, Grafana, Loki)

Use this when you want **metrics** (Prometheus), **dashboards**, and **searchable logs** (Loki) instead of only `docker compose logs`.

**Environment (see `.env.example`):**

- **`METRICS_ENABLED=true`** — registers **HTTP** metrics and **Ask-pipeline** counters/histograms, and serves **`GET /metrics`** for Prometheus to scrape.
- **`LOG_JSON=true`** *(optional but recommended with Loki)* — one JSON object per line for `ask_trace` events (easier **LogQL** / `| json` in Grafana Explore).

**Start the stack** (core services + observability; from repo root):

```bash
docker compose --profile observability up -d
```

**URLs (defaults):**

| What        | URL |
|------------|-----|
| Grafana    | [http://localhost:3000](http://localhost:3000) (anonymous admin enabled for local dev) |
| Prometheus | [http://localhost:9090](http://localhost:9090) |
| Loki       | [http://localhost:3100](http://localhost:3100) (API; browse logs in Grafana) |
| App metrics| [http://localhost:8000/metrics](http://localhost:8000/metrics) (only when `METRICS_ENABLED=true`) |

**Quick checks:**

1. **Scrape / metrics**

   ```bash
   curl -sS 'http://localhost:8000/metrics' | head -40
   ```

   **Expect:** Prometheus text (e.g. `http_requests_total`, `ledgerly_retrieval_gate_total`, histogram `_bucket` lines) if metrics are enabled and the app is up.

2. **Grafana dashboard** — open **Dashboards** → **Ledgerly — HTTP & Ask pipeline** (provisioned JSON). Panels include HTTP rate/latency, retrieval-gate rate, retrieve/LLM duration quantiles, and a Loki logs panel filtered to the **`ledgerly-app`** container.

3. **Correlate a manual Ask call** — repeat **Step 2** (or **Step 3** / **4**) and note **`X-Request-ID`**. In **Grafana → Explore → Loki**, query logs for that container; with **`LOG_JSON=true`**, you can use **LogQL** such as `| json` and filter on `request_id` once labels/JSON parsing are applied.

**Promtail** (in this profile) reads the **Docker** socket and **keeps** only the **`ledgerly-app`** container, and sets the **`container`** label to `ledgerly-app` for queries like `{container="ledgerly-app"}`.

---

## Step 9 — Automated tests (pytest)

Run **Ask trace**, **observability metrics**, and **ask graph** unit tests from the repo root (use a venv if your system Python is externally managed):

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/test_ask_trace.py tests/test_observability_metrics.py tests/test_ask_graph_unit.py -q
```

**Expect:** all tests pass. **`METRICS_ENABLED`** defaults **off** in tests; `test_observability_metrics` checks that domain metric helpers **do not throw** when metrics are disabled. For a full regression run, use `pytest` without narrowing the file list.

---

## Step 10 — Optional API discovery

FastAPI serves **OpenAPI** docs if enabled in your run configuration:

- Interactive: `http://localhost:8000/docs`
- Raw schema: `http://localhost:8000/openapi.json`

Use these to confirm field names and try requests from the browser.

---

## Related project docs

- Broader debugging for weak or missing context: [docs/debugging-not-enough-context.md](docs/debugging-not-enough-context.md)
