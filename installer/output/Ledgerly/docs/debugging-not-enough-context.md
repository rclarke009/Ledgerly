# Debugging “not enough context” answers

Ledgerly’s **Ask** path can feel like “no context” in two different ways. Use this guide to find **which case you have**, then pull the **right logs** (Docker locally; Supabase only if you enabled remote telemetry).

---

## Step 1: Name what the UI actually showed

Note the **exact answer text** and whether **Source chunks** appeared.

| What you saw | Meaning |
|--------------|---------|
| **“I don't have relevant context or data to answer that question.”** and **zero** Source chunks | The backend decided **`has_context` is false**: nothing useful was assembled into the prompt (no doc chunks block, no data summary block, no finance-tool block—or all were empty). See [Step 3](#step-3-when-has_context-is-false-no-docdata-in-prompt). |
| An answer **in the assistant’s voice** (“The context doesn’t include…”) but **chunks may exist** | The LLM answered from a prompt that included context; retrieval may have succeeded but the passages don’t answer the question. See [Step 4](#step-4-when-chunks-exist-but-the-answer-is-weak). |
| **HTTP error** / **timeout** / “Internal server error” / **504** | Infrastructure or LLM errors. See [Step 5](#step-5-when-you-suspect-real-errors-not-rag).

---

## Step 2: Watch Ledgerly logs while reproducing

The API logs **INFO** lines for every `/ask` and `/ask/stream` completion. Locally (venv) they go to the terminal running `uvicorn`. In Docker they go to the **`ledgerly` service** stdout.

Reproduce the question once while tailing logs (Docker commands below). Then search the output for lines containing **`Ask:`** or **`Ask/stream:`**.

You care about lines like:

- **`graph build done in … ms route=… chunks=N`** — `chunks` is how many retrieved passages were attached; `route` is how the question was classified (`docs_only`, `data_only`, or `both`).
- **`early return (no context)`** — confirms the **fixed** no-context reply ( **`has_context` false** ).
- **`LLM done in … ms`** — the model ran; a vague answer is usually **semantic**, not a missing-exception.

---

## Step 3: When `has_context` is false (no doc/data in prompt)

Typical causes:

1. **No documents ingested**, or ingestion didn’t produce chunks/embeddings for the DB Docker Compose uses.
2. **Route `data_only`** but there is nothing in your financial Layer‑2 tables to summarize (and no tool block).
3. **Retrieval returned no rows** after retry logic (embedding/query issue, empty chunk table).
4. **Chunk scores very low**: the graph **retrieves again once** when the best score is below `0.22` or when there were no chunks; if the second pass still yields nothing usable, context can remain empty depending on route and other blocks.

**Docker — app logs**

1. From the directory that contains `docker-compose.yml`:
   ```bash
   docker compose logs -f ledgerly
   ```
2. Optionally only recent lines:
   ```bash
   docker compose logs --tail=200 ledgerly
   ```
3. Compose service name is `ledgerly`; the container name from this repo’s compose file is often **`ledgerly-app`**, so either works:
   ```bash
   docker logs -f ledgerly-app
   ```

Filter mentally (or with `grep`) for `Ask:` / `Ask/stream:` and `chunks=`.

**Other Docker services**

- **`ollama`**: embedding or LLM failures often show here if the app logs aren’t explicit enough.
   ```bash
   docker compose logs --tail=100 ollama
   ```
- **`postgres`**: only needed if you suspect DB connectivity or migrations; the app connects as `ledgerly@postgres`.
   ```bash
   docker compose logs --tail=100 postgres
   ```

**Quick data checks**

- UI **Documents** tab or **`GET /documents`** — confirm docs exist with non‑zero chunk counts for the DB your container uses.
- If you use **`use_rag: false`** in API calls (not the default UI), doc retrieval is skipped — easy to confuse with “no context.”

---

## Step 4: When chunks exist but the answer is weak

Expand **Source chunks** in the UI (or inspect the **`top_chunks`** field from the API).

- **Empty or irrelevant chunks**: query phrasing vs ingested content, wrong document scope, or embedding mismatch (different `EMBED_MODEL` than used at ingest hurts badly).
- **Good chunks but LLM still hedges**: model behavior or prompt limitations; Docker logs showing a positive **`chunks`** count plus **`LLM done`** confirms the pipeline ran.

---

## Step 5: When you suspect “real errors” (not RAG)

### A. Docker (always available when you run Compose)

Unhandled exceptions and LLM client failures log **`logger.exception`** or **`logger.warning`** in the app container. Tail **`ledgerly`** as in Step 2.

HTTP-level outcomes that map to **`send_remote_log`** (remote telemetry):

- **504** — LLM timeout handlers  
- **503** — LLM service unavailable  
- **429** — rate limiting  
- **500** — unhandled exceptions (truncated detail to client; full traceback in Docker logs)

The **friendly** “no context” early return does **not** send a row to Supabase — it’s an intentional **INFO** log line, not an error.

---

### B. Supabase — `remote_log_events` (optional; only if configured)

Hosted logging is **separate from `DATABASE_URL`**. Rows appear only when:

1. You set **`REMOTE_LOG_URL`** (and optionally **`REMOTE_LOG_SECRET`**) in Ledgerly’s `.env`, and  
2. You deployed **`ingest-remote-log`** and applied the **`remote_log_events`** migration on that Supabase project (see **[`supabase/README.md`](../supabase/README.md)** and **Hosted Supabase logging** in **[`setup_and_testing.md`](../setup_and_testing.md)**).

**Where to look in Supabase**

1. **Dashboard → Table Editor → `remote_log_events`**
   - Sort by **`received_at`** descending.
   - Useful columns: **`level`**, **`error_type`**, **`message`**, **`route`**, **`duration_ms`**, **`instance_id`**, **`stack_trace`** (when present).

2. If the table is empty but you expected errors:
   - Confirm **`REMOTE_LOG_URL`** matches `https://<PROJECT_REF>.supabase.co/functions/v1/ingest-remote-log`.
   - Restart the app container after changing `.env`.
   - **`remote_log`** is **fire-and-forget** — network issues won’t rollback your request but also won’t show in the table.

**Edge Function “real errors” (delivery failures)**

Problems **accepting or inserting** payloads show in Supabase itself, not in Ledgerly Docker logs:

1. **Dashboard → Edge Functions → `ingest-remote-log` → Logs**  
   - Look for 401/secret mismatch, runtime errors in the function, or database insert failures.

**Not the same thing**

- **`remote_log_events`** — application-level errors Ledgerly chose to report (timeouts, 500s, etc.).
- **`DATABASE_URL`** pointing at Supabase — your **normal app data**. Use Supabase **SQL Editor**, **Reports**, or **Logs** for **Postgres** issues (slow queries, connection limits) if that’s where your ledger lives — that’s orthogonal to **`REMOTE_LOG_URL`**.

---

## Short checklist

1. Read the **exact** user-facing message (fixed sentence vs LLM wording).  
2. **`docker compose logs -f ledgerly`** → find **`Ask:`** / **`Ask/stream:`** → note **`chunks=`** and **`early return (no context)`**.  
3. **`GET /documents`** / Documents tab → data actually present?  
4. If you enabled **`REMOTE_LOG_URL`**, **`remote_log_events`** + Edge Function logs for infrastructure errors; otherwise rely on Docker **/`ollama`** logs.

Related internal notes: **`docs/testing/langgraph-rag-testing-plan.md`** (ask graph behavior and log strings).
