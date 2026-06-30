Ledgerly: SQLite → Supabase (Postgres + pgvector) migration plan
Goal: Run Ledgerly on Supabase: Postgres + pgvector for documents, chunks, and embeddings. Keep existing app behavior (ingest, list docs, ask/RAG) with DB-backed vector search and no 5k cap.

**Implemented in app (when `DATABASE_URL` is set):** `app/main.py` uses `app_db_connection()` (Postgres via psycopg or SQLite from `DATABASE_PATH`). `app/retrieval.py` calls `db_postgres.retrieve_top_k` for pgvector (`<=>`, score `1 - distance`) with no 5k cap; SQLite still uses `get_embeddings_for_retrieval` + in-Python cosine + cap. CRUD is implemented in `app/db_postgres.py` and dispatched from `app/db.py`. On first connect, `ensure_postgres_schema()` creates extension/tables/indexes (including HNSW) if missing—**Supabase-hosted projects** should still apply migrations in `supabase/migrations/` (especially `20250320000000_schema_parity_content_hash_tags.sql` for `content_hash` and `document_tags`).

Current state (reference) — **SQLite default (no `DATABASE_URL`):**
Schema: documents (incl. `content_hash`), chunks, embeddings (`vector_json TEXT`), `document_tags`, financial tables. Indexes on chunks(doc_id), (doc_id, chunk_index).
Embedding: nomic-embed-text → 768 dimensions (see `app/embeddings.py`).

**Postgres:** `embeddings.embedding vector(768)`; run migrations for parity with SQLite (`document_tags`, `documents.content_hash`).
Phase 1 — Supabase project and schema
Create a Supabase project (supabase.com → New project). Note:
Project URL (e.g. https://xxxx.supabase.co)
Database password (for direct Postgres)
API: anon key and (for backend) service_role key (Project Settings → API).
Enable pgvector (often already on; if not):
In SQL Editor run:
CREATE EXTENSION IF NOT EXISTS vector;
Create tables in Supabase (SQL Editor). Match your current schema but store the embedding as a vector column (no JSON):
documents: doc_id (TEXT PK), title TEXT, source TEXT, created_at BIGINT (or TIMESTAMPTZ if you prefer).
chunks: chunk_id TEXT PK, doc_id TEXT, chunk_index INT, content TEXT, start_offset INT, end_offset INT. Index on doc_id and (doc_id, chunk_index).
embeddings: chunk_id TEXT PK, model TEXT, embedding vector(768) (not JSON), dim INT. Optional: index on model if you filter by it.
Add vector index for retrieval. After you have (or will have) rows in embeddings, create an HNSW index for cosine distance, e.g.:
   CREATE INDEX ON embeddings   USING hnsw (embedding vector_cosine_ops);
(Use your actual table/column names; pgvector uses <=> for cosine distance.)
Connection: For the FastAPI app you need a Postgres connection string. Use either:
Direct Postgres: Project Settings → Database → Connection string (URI), e.g. postgresql://postgres.[ref]:[PASSWORD]@aws-0-[region].pooler.supabase.com:6543/postgres. Use this with psycopg2 or asyncpg.
Supabase client (optional): For REST/Realtime you’d use the JS client; for Python server-side RAG, a direct DB connection is simpler and matches your current “conn” style.
**Where to set it:** In `Ledgerly/.env` set `DATABASE_URL=<paste the Postgres URI>`. The app reads it from `app/config.py`. When set, the app uses Postgres for all DB access and pgvector for RAG retrieval.  
**URI vs project URL:** The URI is *not* the project URL you see in the portal (e.g. `https://xxxx.supabase.co`). Go to **Project Settings → Database** and find the **Connection string** section; choose the **URI** format (starts with `postgresql://`). Replace `[YOUR-PASSWORD]` with your database password.

Phase 2 — Config and dependencies
Environment: Add to .env (and document in setup_and_testing.md or similar):
DATABASE_URL=postgresql://... (Supabase Postgres URI; use pooler if you have many short-lived connections).
Optionally keep DATABASE_PATH for a future “local SQLite fallback” if you want.
Config (app/config.py):
Read DATABASE_URL from env (no default, or default to empty to force explicit choice).
Keep existing embedding/LLM/Google vars; only DB connection changes.
Dependencies: Add a Postgres driver. For synchronous style (like your current SQLite):
psycopg2-binary (or psycopg if you prefer).
Or for async later: asyncpg.
Add to requirements.txt and install.
Phase 3 — DB layer (app/db.py)
Connection lifecycle: Replace “open SQLite from path” with “open Postgres from DATABASE_URL.” For example:
At startup (lifespan): create a connection pool or a single connection (depending on your concurrency). Store it on app.state (e.g. app.state.db_pool or app.state.db_conn).
On each request that needs DB: get a connection from the pool (or use the single conn if that’s your design). No more sqlite3.connect(app.state.db_path) in route handlers.
Schema creation: Replace create_db(conn) so it runs Postgres DDL:
CREATE TABLE IF NOT EXISTS documents (...);
CREATE TABLE IF NOT EXISTS chunks (...);
CREATE TABLE IF NOT EXISTS embeddings (...);
Same indexes as above.
CREATE EXTENSION IF NOT EXISTS vector if you prefer to do it from app (otherwise keep it as a one-off in Supabase SQL Editor).
CRUD and retrieval:
insert_document / insert_chunk: Same logic, use parameterized Postgres (e.g. %s for psycopg2).
insert_embedding: Instead of vector_json TEXT, INSERT the vector directly. With psycopg2 you can pass a list of floats and cast to vector(768) in SQL, or use a type adapter. Column: embedding vector(768).
doc_exist: Same logic, SELECT 1 FROM documents WHERE doc_id = %s.
delete_by_doc_id: Same order: delete from embeddings (where chunk_id in chunks for doc_id), then chunks, then documents. Use one transaction.
list_documents: Same query shape; Postgres supports the same subqueries (count chunks, first chunk content). Use parameterized SQL.
Retrieval (replaces “load all + score in Python”): Add a function that runs vector search in Postgres, e.g.:
Name: e.g. retrieve_top_k_supabase(conn, query_vec, top_k, doc_id=None) or replace get_embeddings_for_retrieval with a function that returns top-k by similarity.
Query:
Embeddings joined to chunks (and optionally documents).
ORDER BY e.embedding <=> %s::vector LIMIT %s (cosine distance; %s is the query vector as a string like '[0.1, -0.2, ...]' or bound as vector).
If doc_id is provided, add WHERE c.doc_id = %s.
Return: Same shape as today: list of (chunk_id, doc_id, score, content). For cosine similarity you can use 1 - (e.embedding <=> $1) so higher = more similar. Return that as score.
Phase 4 — Retrieval and main app
app/retrieval.py:
Change retrieve_top_k to use the new DB function: call the Postgres vector-search helper instead of get_embeddings_for_retrieval + Python loop.
Signature: Keep retrieve_top_k(db, query_vec, top_k, doc_id=None) so main.py doesn’t need to change call sites. db here is the Postgres connection (or pool-issued conn).
Remove the 5k cap and in-Python scoring; the DB returns only top-k.
Still return list[RetrievedChunk] with chunk_id, doc_id, score, content_snippet (e.g. left(content, 500)).
app/main.py:
Lifespan: Stop creating SQLite file and sqlite3.connect. Create Postgres pool (or conn) from config.DATABASE_URL, run create_db (Postgres DDL), store pool/conn on app.state. On shutdown, close pool/conn.
Routes: Where you currently do with sqlite3.connect(request.app.state.db_path) as conn:, instead get a connection from app.state (e.g. conn = request.app.state.db_pool.getconn() and later return it to the pool, or use a single shared conn if that’s your design).
Ingest, list, delete, ask: pass this conn into the same db and retrieval functions. No change to request/response models.
Optional: Keep app/similarity.py for tests or local fallback; the main path no longer uses it for retrieval once Postgres does the similarity.
Phase 5 — Data migration (if you have existing SQLite data)
Export from SQLite: Script or one-off: read from documents, chunks, embeddings (parse vector_json to list of floats).
Import to Supabase: Insert into documents, then chunks, then embeddings (embedding column = vector(768)). Use the same transaction per doc if you want consistency.
Verify: Row counts, and run one ask (e.g. “What does my statement say about CD maturity?” or “Summarize the fees in my documents”) and compare results/timing.
Phase 6 — Testing and docs
Tests: If you have tests that use SQLite (e.g. in-memory or a test file), add a path or env to run against Supabase (e.g. a separate test project or a TEST_DATABASE_URL). Update tests to use the new connection and vector retrieval.
Docs: Update setup_and_testing.md (or equivalent) with:
Supabase project setup, pgvector, and the exact table/index SQL.
Required env vars (DATABASE_URL).
How to run ingest and ask locally against Supabase.
Optional: how to run the migration script for existing SQLite data.
Checklist (summary)
[ ] Supabase project created; pgvector enabled; tables + indexes created (including vector(768) and HNSW). Apply `20250302000000`, `20250308000000`, `20250320000000` migrations (or rely on `ensure_postgres_schema` for empty local Postgres only).
[x] DATABASE_URL in env; config reads it; `requirements.txt` includes `psycopg[binary]`.
[x] `db_postgres.py` + dispatch in `db.py`; vector top-k in `retrieve_top_k` for Postgres.
[x] `retrieval.py`: Postgres path uses SQL only; no 5k cap; same `retrieve_top_k` signature.
[x] `main.py`: `DATABASE_URL` → psycopg per request via `app_db_connection`; SQLite uses `DATABASE_PATH`.
[ ] Optional: migration script SQLite → Supabase for existing data.
Use this as your guide; implement phase by phase and test ingest + list + ask after each phase. If you want this turned into a SUPABASE-MIGRATION.md (or similar) in the repo, switch to Agent mode and ask to add it.