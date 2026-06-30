# Ledgerly — Build Prompts (Junior-Dev Guide)

Work through these in order. Each prompt tells you *what* to build and *why* it comes now, without writing every line for you. Use `overview.md` and `code-notes.md` for context.

---

## 1. Project setup and layout

Create the Ledgerly project shell: a directory (e.g. `Ledgerly/app/` or `Ledgerly/` at repo root), a virtualenv, and a `requirements.txt` with the dependencies you know you’ll need (FastAPI, Pydantic, an async HTTP client if you’ll call an embedding API, and anything for SQLite). Add a minimal `main.py` that runs a FastAPI app and mounts a health or root route so you can start the server and see a response.

**Why first:** Everything else depends on being able to run the app and import from your modules. Get the skeleton and “it runs” out of the way.

**Check:** From the project root, `python -m uvicorn app.main:app --reload` (or your entrypoint) returns something like 200 OK.

---

## 2. Config and environment

Add a small config module that reads from the environment: things like database path, embedding model name and (if you use a remote API) base URL and API key. Use sensible defaults where safe (e.g. a local SQLite path); never default secrets. Keep config in one place so the rest of the app doesn’t touch `os.environ` directly.

**Why now:** Ingest and ask will need DB path and embedding/LLM settings. Centralizing config now avoids scattering env reads later.

**Hint:** If you’ve done the ai-document project, reuse the same pattern (e.g. a `config.py` with a dataclass or Pydantic settings). **Models:** Target **Qwen3 8B** (`qwen3:8b`) via Ollama for the LLM (local, for client-name privacy); vision uses **`LLAVA_MODEL`** on Ollama (e.g. `llava:7b`) for image → report. Config should support an LLM base URL (e.g. `http://localhost:11434`) and model name (e.g. `qwen3:8b`).

---

## 3. Request and response models (Pydantic)

Define Pydantic models for the two main flows. For **ingest:** a request body with at least `text` (required), and optional `doc_id`, `title`, `source`, and chunking options (e.g. `chunk_size`, `chunk_overlap`). Define a response that includes `doc_id`, `num_chunks`, and whatever embedding metadata you plan to return. For **ask:** a request with `question`, optional `top_k` and optional `doc_id` (to restrict search to one document), and a response with `answer` and a list of retrieved chunks (each with something like `chunk_id`, `doc_id`, `score`, and a short `content_snippet`).

**Why now:** The API contract drives the rest of the implementation. Nail the shapes of ingest and ask before you wire DB or business logic.

**Hint:** See the Phase 3 spec in `ai-document/phase3.md` (IngestRequest/IngestResponse, AskRequest/AskResponse, RetrievedChunk) and adapt names or fields to Ledgerly if you like.

---

## 4. Database schema and a small DB layer

Design the SQLite schema: tables for **documents** (e.g. `doc_id`, `title`, `source`, `created_at`), **chunks** (e.g. `chunk_id`, `doc_id`, `chunk_index`, `content`, `start_offset`, `end_offset`), and **embeddings** (e.g. `chunk_id`, `model`, `vector_json`, `dim`). Add indexes that support “get chunks by doc_id” and “get embedding by chunk_id.” Implement a thin DB module that opens the DB, creates tables if they don’t exist, and exposes a few helpers (e.g. insert document, insert chunks, insert embeddings, fetch embeddings for retrieval). Keep it synchronous and simple unless you already know you want async.

**Why now:** Chunking and ingest will need to persist documents and chunks; retrieval will need to load embeddings. Doing the schema and helpers now makes the next steps straightforward.

**Check:** You can open the DB, create tables, insert one row into each table, and read it back (by hand or a tiny script).

---

## 5. Chunking

Implement a function that splits a long string into chunks by character count, with a fixed overlap between consecutive chunks. It should return a list of chunk objects that include at least `chunk_index`, `content`, `start_offset`, and `end_offset`. Enforce that overlap is less than chunk size; the last chunk may be shorter. Optionally add a test: for a short string and given `chunk_size` and `overlap`, the start offsets and content match what you expect.

**Why now:** Ingest will call this before storing chunks and embedding them. Chunking has no dependency on the API or DB beyond the shape of the chunk; doing it here keeps the ingest flow easy to follow.

**Hint:** The Phase 3 spec describes `chunk_text_chars(text, chunk_size, overlap)` and the offset rules. Use that as the contract.

---

## 6. Embedder interface and a first implementation

Define a small abstraction for “turn a list of strings into a list of vectors”: e.g. an `Embedder` with something like `embed_many(texts: list[str]) -> list[list[float]]`, plus `model` and `dim` so the rest of the app knows the embedding model and dimension. Implement a first version: either a **stub** that returns deterministic same-dimension vectors (e.g. from a simple hash of the text) so you can run the full pipeline without an API, or a real client that calls an embedding API. Prefer starting with the stub so you can finish ingest and ask end-to-end, then swap in the real embedder.

**Why now:** Ingest needs to embed chunks before storing; ask needs to embed the question. Having one interface lets you switch implementations without changing the rest of the code.

**Hint:** See `code-notes.md` for library suggestions (e.g. pypdf, PyMuPDF) for *files*; for embeddings, use whatever your ai-document project used (e.g. OpenAI-style API) or the Phase 3 stub idea.

---

## 7. Cosine similarity and retrieval

Implement a function that computes cosine similarity between two vectors (same length), and handle the case where a vector has zero length so you don’t divide by zero. Then implement retrieval: given a query vector, load the stored chunk embeddings (optionally filtered by `doc_id`), compute similarity of the query to each, sort by score descending, and return the top-k chunks with their content and scores. Return structures that match what your ask response needs (e.g. chunk_id, doc_id, score, content_snippet). Cap the number of candidates (e.g. 5k) if you’re loading all into memory so you don’t blow up on huge DBs.

**Why now:** Ask will “embed question → retrieve top-k → send to LLM.” Retrieval is the bridge between the query vector and the chunks you’ll put in the prompt.

**Check:** With a few chunks and embeddings in the DB, you can call your retrieval function with a query vector and get back the expected top-k (e.g. by embedding a sentence and checking that the chunk containing that sentence ranks high).

---

## 8. POST /ingest

Wire the ingest endpoint: validate the request body with your Pydantic model; chunk the `text` with your chunking function; insert one row into the documents table; insert one row per chunk into the chunks table; call your embedder for all chunk texts; insert one row per chunk into the embeddings table; return your ingest response. Decide and document: if `doc_id` already exists, do you return an error (e.g. 409) or overwrite? If embedding fails after you’ve written documents/chunks, do you roll back or leave partial data? Prefer “reject duplicate doc_id” and “roll back or don’t persist on embed failure” so the DB stays consistent.

**Why now:** This is the first end-to-end flow: text in, chunks and embeddings stored. Getting it right here makes the rest of the app usable.

**Hint:** You can use a single transaction (begin, insert doc + chunks + embeddings, commit) and roll back on any failure, or explicitly delete the document and its chunks if embedding fails. Document your choice in a comment or in `code-notes.md`.

---

## 9. POST /ask

Wire the ask endpoint: validate the request; embed the question with the same embedder you use for chunks; call your retrieval function to get top-k chunks; build a prompt that includes a short system instruction (e.g. “You suggest report wording based on the following context”), the user’s question, and a “Context:” section with the retrieved chunks (include doc_id and maybe chunk_id so the model can refer to sources). Call your LLM with that prompt and return the model’s answer plus the list of top chunks (and optionally scores/snippets). Cap the total context length (e.g. character or token limit) so you don’t exceed model limits. If retrieval returns no chunks, either return a message like “I don’t have relevant context” or call the LLM without context and say so in the prompt.

**Why now:** This completes the RAG loop: question → embed → retrieve → prompt with context → LLM → answer. Ledgerly’s value is “ask for overview/detail wording and get it from similar reports.”

**Hint:** Reuse your ai-document LLM client or a minimal async caller; point it at **Ollama** (e.g. `http://localhost:11434`) and use **Qwen3 8B** (`qwen3:8b`) so all generation stays local for client-name privacy. Keep the prompt template in one place so you can tune it later for “overview and detailed image wording.” Vision: **`LLAVA_MODEL`** on Ollama for “look at this job’s images and write report text.”

---

## 10. GET /documents (list ingested)

Add an endpoint that returns a list of what has already been ingested so users can see what’s in the system (confirm uploads, spot duplicates, scan by title). Implement **GET /documents** (or **GET /ingest** if you prefer) that queries the documents table and returns a list of items. Each item should include at least: `doc_id`, `title`, `source`, `created_at`, and `num_chunks`. Optionally include a short `snippet` (e.g. first 200–300 characters of the document text, or of the first chunk’s content) so users get a quick preview. Define a Pydantic response model (e.g. `DocumentSummary` with those fields) and a list response (e.g. `DocumentsListResponse` with `documents: list[DocumentSummary]`). Add a DB helper that selects from `documents` and optionally joins with the first chunk per doc for the snippet; keep the query simple (e.g. order by `created_at` desc).

**Why now:** Users need to answer “what have we already ingested?” without re-uploading or guessing. Doing it right after ask keeps the API surface complete for the core RAG + discovery flow.

**Check:** After ingesting a few reports, call GET /documents and confirm the list shows the expected titles, counts, and (if implemented) snippets.

---

migrating to supabase (see supabase_migration.md)

## 11. (Optional) File extraction and batch ingest

Add a step that reads report files from disk: for each PDF or .docx path, extract plain text (and optionally title/source from filename or metadata), then call your ingest logic (same chunk → embed → store) as if that text had been sent in the request body. You can expose this as a CLI script, a separate endpoint like POST /ingest/file, or a background job. Use the libraries mentioned in `code-notes.md` (e.g. pypdf or PyMuPDF for PDF, python-docx for .docx); do not support .pages for this pipeline.

**Why last:** The core app is ingest + ask over text. File extraction is a convenience layer on top so you can point at a folder of reports and bulk-load them.

**Check:** Run your extractor on a few PDFs and .docx files; confirm the text looks correct and that after “ingest,” asking a question returns relevant chunks from those documents.

---

## After you’re done

- Try a few ask queries that are clearly about “give me overview/detail wording for [symptom]” and see if the retrieved chunks and answers match what you expect.
- Optionally add a flag or query param to call the LLM with the question only (no context) so you can compare RAG vs no-RAG.
- Note any follow-ups (e.g. chunk size, overlap, prompt wording, or moving to pgvector) in `code-notes.md` for the next iteration.



## overview:

Project setup — venv, layout, minimal FastAPI, “it runs”
Config — env-based config in one place (LLM: Ollama + **Qwen3 8B**; vision: **`LLAVA_MODEL`**)
Pydantic models — ingest & ask request/response shapes
DB schema + helpers — documents, chunks, embeddings tables and a thin DB layer
Chunking — character-based chunking with overlap and offsets
Embedder — interface + stub (or real API) so you can swap later
Cosine similarity + retrieval — top-k over stored embeddings
POST /ingest — chunk → embed → store; doc_id and failure policy
POST /ask — embed question → retrieve → prompt with context → **Qwen3 8B** (Ollama) → response
GET /documents — list ingested docs (doc_id, title, source, created_at, num_chunks, optional snippet)
(Optional) File extraction — PDF/.docx → text → ingest (CLI or extra endpoint)
**Vision path:** `LLAVA_MODEL` on Ollama for image → report (“look at this job’s images and write report text”)
