# Ledgerly — Overview

See [README.md](README.md) for repo entry and development status.

Ledgerly is a **private cash and document assistant** for your own machine: it helps track **safe-income holdings** (CDs, money markets, and similar), **ingests financial documents** for search and Q&A, and surfaces **trigger-style guidance** (for example, CDs approaching maturity or obligations coming due). See **[FINANCIAL-ASSISTANT.md](FINANCIAL-ASSISTANT.md)** for product principles, privacy stance, and API orientation.

---

## What it does

- **Data** — Define **accounts** (per institution), **positions** (individual CDs, funds, etc.), and **obligations** (bills or deadlines). Optional links to ingested documents keep paperwork and numbers aligned.
- **Ingest** — Upload PDFs or images, or paste text. Content is chunked, embedded with a local model, and stored for retrieval alongside your structured data.
- **Documents** — Inspect what is in the system: titles, IDs, tags, optional vault paths, and snippets.
- **Ask** — Ask natural-language questions over **your saved financial data and ingested documents** (RAG + tools as configured). You can limit answers to a single document or tag.
- **Status / Past advice** — Run decision checks on your positions and obligations and review historical memos (exact behavior depends on your rules and LLM configuration).

Prior versions of this file described a storm-damage–report demo domain; the **current** focus is personal finance and document assistance as above.

---

## Typical stack (Docker Compose)

From the repo root (with Docker running):

```bash
./start.sh          # Mac/Linux — pulls models and waits for health
# Start.bat         # Windows
```

Manual alternative: `docker compose up -d` plus one-time `ollama pull` (see [setup_and_testing.md](setup_and_testing.md)).

The bundled layout runs the **web app**, **Postgres + pgvector**, **Ollama** (text, embeddings, and vision for scans), and an optional **finance-tools** sidecar. First start may pull **large** container images and AI models—see **[install-instructions.md](install-instructions.md)** (portable) or **[setup_and_testing.md](setup_and_testing.md)** (developers).

Native install without Docker is also supported: Python venv, `pip install -r requirements.txt`, local or remote Ollama for `LLM_*` / `EMBED_*`, and SQLite or Postgres per **[.env.example](.env.example)**.

---

## Architecture (summary)

- **POST /ingest**, **POST /ingest/pdf**, **POST /ingest/image** — Add text or files; chunk → embed → store.
- **POST /ingest/jobs** — Queue multiple files for background processing (UI uses this for multi-select uploads).
- **GET /documents** — List ingested documents and metadata.
- **POST /ask**, **POST /ask/stream** — Retrieve relevant chunks and produce answers (streaming optional).
- **GET /health** — Liveness for the web process (used by the static UI on load).

Storage: **SQLite** when `DATABASE_URL` is unset (simple local runs), or **Postgres + pgvector** in Compose for production-style setups.

Tech: **FastAPI**, **Pydantic**, async HTTP clients for embeddings and LLM calls; **Ollama** defaults: `qwen3:8b` (text), `nomic-embed-text` (embeddings), vision model from config (e.g. `llava:7b` or a smaller profile default).

---

## Roadmap direction

- Hardening: caching, observability, optional API auth for exposed deployments.
- Deeper financial tooling and clearer empty states when optional services (e.g. market quotes) are unavailable.
