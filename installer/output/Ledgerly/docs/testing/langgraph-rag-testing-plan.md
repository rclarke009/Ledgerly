# LangGraph routing + 2-pass RAG testing plan

## Scope

This document defines a test plan for the **LangGraph-based query routing** and **2-pass (multi-step) RAG** behavior used by the API endpoints:

- `POST /ask` (JSON response)
- `POST /ask/stream` (NDJSON streaming response)

The orchestration is implemented in:

- `app/ask_graph.py` (LangGraph nodes + routing + retrieval retry)
- `app/main.py` (API endpoints that call `build_prompt_and_chunks`)

## System behavior under test (as implemented)

### Routing

Routing happens in `app/ask_graph.py::_classify_route`:

- Uses an LLM prompt (`CLASSIFIER_PROMPT`) to produce a single token route:
  - `data_only`
  - `docs_only`
  - `both`
- If the classifier returns anything else, routing **defaults to** `both`.
- If `AskRequest.use_rag == False`, routing is forced to **`data_only`** and doc retrieval is skipped.

### 2-pass (multi-step) retrieval

Retrieval happens in `app/ask_graph.py::_retrieve_docs` with a retry gate in `_need_more_context`:

- **Pass 1 (attempt 0)**:
  - Uses request filters via `_resolve_filter_doc_ids`:
    - `doc_ids` (highest priority)
    - else `tag` (resolved via `app.db.get_doc_ids_by_tag`)
    - else `doc_id`
    - else no filter (all docs)
  - Retrieves `initial_k` candidates and optionally reranks.
- **Pass 2 (attempt 1, broadened)**:
  - Ignores doc filters (**searches all docs**)
  - Increases `initial_k` (doubles, capped at 100)

Retry condition in `app/ask_graph.py::_need_more_context` (deterministic; no extra LLM call):

- Retries if:
  - no chunks returned, **or**
  - best chunk score `< 0.22`
- Retries at most once (max **2 retrieval passes total**).

### Context/prompt construction

Prompt is built in `app/ask_graph.py::_build_context_and_prompt`:

- Includes a short “Your data …” block if route is `data_only` or `both`.
- Includes doc chunk blocks if route is `docs_only` or `both`.
- Enforces a context cap: `MAX_CONTEXT_CHARS = 8000`.
- Sets `has_context` true only if at least one data/doc block was included.

### API early return when no context

In `app/main.py`, both `/ask` and `/ask/stream` return a fixed message when `has_context` is false:

- `/ask`: returns `AskResponse(answer=..., top_chunks=[])`
- `/ask/stream`: returns a single NDJSON line including `{top_chunks: [], answer: ..., done: true}`

## Test environments

### Unit tests (deterministic; no Ollama)

Goal: validate **graph logic, branching, filter precedence, and retry decisions** without network calls.

Strategy:

- Monkeypatch:
  - `app.llm_client.answer_with_context` (route classifier)
  - `app.embeddings.HttpEmbedder.embed_many` (query embedding)
  - `app.ask_graph.retrieve_top_k` and/or `app.retrieval.retrieve_top_k` (retrieval results)
  - `app.ask_graph.rerank` (when testing rerank paths)

### Integration tests (local Ollama; realistic behavior)

Goal: validate the end-to-end experience with:

- SQLite DB schema from `app.db.create_db`
- real embeddings via `app.embeddings_client.embed_texts` against Ollama (`/api/embed`)
- routing + generation via Ollama chat (`/api/chat`)

Default config assumptions (can be overridden by env vars; see `app/config.py`):

- `EMBED_BASE_URL=http://localhost:11434`, `EMBED_MODEL=nomic-embed-text`
- `LLM_BASE_URL=http://localhost:11434`, `LLM_MODEL=qwen3:8b`
- `RERANK_ENABLED` optionally enabled/disabled

## Test data setup

### SQLite fixture DB

For both unit/integration tests, use a fresh SQLite DB per test run:

- Call `app.db.create_db(conn)` to create schema.
- Use a temporary path (e.g., `tmp_path / "test.sqlite"`), and connect with `sqlite3.connect(path)`.

### PDF fixtures and RAG validation

- **LangGraph / RAG behavior** (routing in `app/ask_graph.py`, retrieval, 2-pass broadening, filters): Prefer **native text PDFs** (real text layer) or **small pasted ground-truth snippets** ingested via `POST /ingest` so failures reflect graph and retrieval logic, not OCR or vision noise.
- **Scanned / image-like PDFs** (screenshots, scans): Treat as a **separate concern** from graph tests. Use dedicated tests that **mock** `app.pdf_ingest.resolve_pdf_for_ingest` (or the transcription step), or optional integration tests with OCR/vision enabled and fixtures explicitly labeled as scanned-PDF cases.
- Avoid using **large screenshot PDFs** as the primary regression signal for `ask_graph` or RAG unless the test explicitly targets **post-OCR/post-vision** text quality.

### Documents & tags

To exercise filter behavior and 2-pass broadening, seed:

- at least 2 docs with distinct topics (so one doc is irrelevant and the other is relevant)
- tags inserted via `app.db.set_document_tags(conn, doc_id, tags)`
- embeddings present in `embeddings` for each chunk (integration uses real embed; unit can insert fake vectors)

Important implementation details to reflect in tests:

- `app.db.get_doc_ids_by_tag` returns doc_ids ordered by doc_id.
- `app.db.get_embeddings_for_retrieval` joins `embeddings` → `chunks` and JSON-decodes vectors.

### Structured “data-only” context

Seed `accounts`, `positions`, `obligations` to ensure `_build_data_summary` produces content:

- create at least one account row
- optionally a position with `maturity_date`
- optionally an obligation with `due_date`

## Test matrix

### A) Routing tests (LangGraph classify + defaults)

- **A1 — `use_rag=False` forces `data_only`**
  - Input: `AskRequest(use_rag=False)`
  - Expect: route `data_only`, retrieval skipped, prompt contains “Your data …”

- **A2 — Classifier returns invalid token → defaults to `both`**
  - Mock classifier output: `"maybe_docs"`
  - Expect: route `both`

- **A3 — Classifier returns `docs_only`**
  - Mock classifier output: `"docs_only"`
  - Expect: route `docs_only` and doc retrieval runs

- **A4 — Classifier returns `data_only`**
  - Mock classifier output: `"data_only"`
  - Expect: route `data_only` and doc retrieval is skipped

### B) Filter precedence tests (doc_ids > tag > doc_id > all)

Implement as unit tests for `_resolve_filter_doc_ids` and integration tests at the API level.

- **B1 — `doc_ids` overrides `tag` and `doc_id`**
  - Input: `doc_ids=["A","B"]`, `tag="t1"`, `doc_id="C"`
  - Expect: filter doc_ids == `["A","B"]` on pass 1

- **B2 — `tag` expands to doc_ids**
  - Seed `document_tags` and call with `tag="t1"`
  - Expect: pass-1 retrieval uses the resolved doc_ids list

- **B3 — `doc_id` used when no doc_ids/tag**
  - Input: `doc_id="D"`
  - Expect: pass-1 retrieval restricted to `"D"`

### C) 2-pass retrieval (retry + broadening)

These are the core multi-step behaviors.

- **C1 — No chunks on pass 1 triggers broaden + pass 2**
  - Setup: pass-1 retrieval returns `[]`
  - Expect: `_retrieve_docs` called twice, second time with broadened behavior (doc_ids ignored)

- **C2 — Low-score pass 1 triggers broaden**
  - Setup: pass-1 returns `[RetrievedChunk(score=0.10, ...), ...]`
  - Expect: retry + second retrieval

- **C3 — Good score pass 1 does not retry**
  - Setup: pass-1 returns `[RetrievedChunk(score=0.30, ...)]`
  - Expect: single retrieval pass

- **C4 — Retry stops after pass 2**
  - Setup: pass-1 empty; pass-2 still empty
  - Expect: graph proceeds to prompt build; no infinite loop

- **C5 — Broadening ignores filters**
  - Setup: request sets `doc_id` to an irrelevant doc; a different doc contains matching chunks
  - Expect: pass-1 empty/low; pass-2 returns chunks from the other doc

### D) Reranker behavior (optional two-stage retrieval)

In `app/ask_graph.py`, initial candidate size depends on:

- `RERANK_ENABLED`
- `RERANK_INITIAL_K_MULTIPLIER` and `RERANK_INITIAL_K_MAX`

Test cases:

- **D1 — Rerank disabled**
  - Ensure retrieval returns at most `top_k` and preserves similarity-based ordering

- **D2 — Rerank enabled uses expanded initial_k then trims to top_k**
  - Confirm `initial_k = min(multiplier*top_k, max)` on pass 1 (and doubled on broaden pass)
  - Confirm rerank called and output length == `top_k`

### E) Prompt/context construction

- **E1 — `data_only` prompt contains only data summary (no doc blocks)**
- **E2 — `docs_only` prompt contains only doc blocks**
- **E3 — `both` prompt contains both**
- **E4 — `MAX_CONTEXT_CHARS` cap enforced**
  - Provide many chunks / large content snippets and ensure the context truncation logic stops adding blocks

### F) API contract tests

#### `/ask`

- **F1 — Response shape**
  - Contains `answer` and `top_chunks` list items matching `RetrievedChunk` schema (`chunk_id`, `doc_id`, `score`, `content_snippet`)

- **F2 — No-context early return**
  - With no docs and no structured data seeded, expect the fixed message and `top_chunks=[]`

#### `/ask/stream`

- **F3 — NDJSON ordering**
  - First line: `{"top_chunks":[...]}` (meta)
  - Subsequent: one or more `{"delta":"..."}` lines
  - Final: `{"done": true}`

- **F4 — No-context streaming early return**
  - Single line containing `top_chunks: []`, `answer: ...`, `done: true`

## Negative / resilience tests

### LLM/embedding outages (local Ollama)

Validate error surfaces (these are handled by exception handlers in `app/main.py`):

- **Embedding API unreachable**:
  - `/ingest` returns `503` (“Embedding failed”)
- **LLM API unreachable**:
  - `/ask` returns `503` (“LLM service unavailable”) or `500` depending on exception type path

### Rate limiting and timeouts

When Ollama returns 429 or request timeouts occur, validate:

- For `/ask`: status codes `429`, `504`, `503` as defined by `app/errors.py` + `app/main.py` handlers
- For `/ask/stream`: stream yields `{"error": "LLM stream failed"}` if an exception occurs mid-stream (see `_stream_ask_generator`)

## Observability checks (logs + remote logs)

### Local logs (always)

Assertions can be lightweight (integration tests can parse stdout logs if desired):

- For `/ask` and `/ask/stream`:
  - `"graph build done ... route=... chunks=..."`
  - `"early return (no context)"` when `has_context` is false

### Remote logs (optional)

If `REMOTE_LOG_URL` is configured, server errors trigger `send_remote_log(...)` in `app/main.py`:

- Validate payload is sanitized (no document content)
- Validate request metadata fields exist (route, request_id/trace_id, duration_ms)

## Non-goals

- Validating the semantic correctness of generated answers beyond minimal “uses context / refuses when missing”.
- Benchmarking latency/throughput (can be added later as a performance suite).

## Runbook (how to run these tests)

### Files you’ll need (beyond the app code)

To *execute* this test plan (not just read it), you typically add:

- **Test runner + dependencies**
  - `requirements-dev.txt` *or* add to `requirements.txt`: `pytest`, `pytest-asyncio`, `anyio`, and `httpx`
  - Optional: `pytest-env` (to inject env vars during tests), `respx` (HTTPX mocking)
- **Test suite skeleton**
  - `tests/` directory
  - `tests/conftest.py` with fixtures:
    - temp SQLite DB path + `sqlite3.connect(...)`
    - `create_db(conn)` call
    - helper to seed docs/chunks/embeddings and accounts/positions/obligations
- **Sample fixtures** (recommended for repeatability)
  - `tests/fixtures/docs/` small `.txt` files (two distinct topics + one “nonsense” doc)
  - `tests/fixtures/questions.json` list of representative questions for each route

You *do not* need any new application code files to run the existing endpoints manually; the above files are for automated testing.

### Prereqs for integration tests (local Ollama)

- **Ollama running** on `LLM_BASE_URL` and `EMBED_BASE_URL` (default `http://localhost:11434`)
- **Models present**:
  - Embeddings: `nomic-embed-text` (default `EMBED_MODEL`)
  - Chat: `qwen3:8b` (default `LLM_MODEL`)

If you use different local models, set env vars before running integration tests:

- `EMBED_MODEL`
- `LLM_MODEL`
- `EMBED_BASE_URL`
- `LLM_BASE_URL`

### Recommended test split

- **Unit tests**: default; fast; no network calls; mock `llm_client` + `HttpEmbedder` + retrieval.
- **Integration tests**: opt-in (e.g., marker like `@pytest.mark.integration`); require local Ollama.

### Manual smoke tests (no new test files required)

These are useful before writing automated tests.

- **1) Start the API**
  - Run the server (whatever you currently use for local dev, e.g. `uvicorn app.main:app --reload`).
- **2) Ingest two docs**
  - Use `POST /ingest` twice with different `doc_id`s; add tags via `tags` field.
- **3) Ask with filters that should fail on pass 1 but succeed on pass 2**
  - `POST /ask` with `doc_id` pointing at the *wrong* doc.
  - Expected signal: server logs show `route=docs_only|both` and `chunks=0` (or low score) then succeed after broadening (you’ll see more chunks in the final response).

### Expected log signals (high-signal)

From `app/main.py`:

- `/ask`: `Ask: graph build done in ... route=... chunks=...`
- `/ask/stream`: `Ask/stream: graph build done in ... route=... chunks=...`
- No-context: `early return (no context)`
- Streaming: `Ask/stream: first LLM delta in ... ms`

### Common failures and how to diagnose

- **All integration tests fail quickly with 503**: Ollama not running or base URL wrong.
- **Ingest fails but ask works**: embedding model missing / embed endpoint failing.
- **Route seems wrong**: classifier LLM output not constrained (tests should mock this in unit tests).
- **2-pass broadening not happening**: pass-1 score isn’t below 0.22; make the “wrong doc” truly irrelevant or use a smaller `top_k` and distinct topics.

- Starting Ollama + ensuring required models are present
- Running unit tests (mocked) vs integration tests (live local Ollama)
- Expected log lines and common failure modes

