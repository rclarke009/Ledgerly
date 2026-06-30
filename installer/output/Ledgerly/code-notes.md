# Ledgerly — Code Notes & Prompts

Implementation decisions and prompts for building the app. Use this when implementing ingest, extraction, or RAG.

---

## Data sources: PDF and .docx only

**Decision:** Ingest report text from **PDF** and **.docx** only. Do not support **.pages** for the pipeline.

**Rationale:**

- We have a PDF (or .docx) for every report; .pages is redundant for ingestion.
- **PDF / .docx** have mature Python libraries (pypdf, PyMuPDF, python-docx); **.pages** requires unzipping and parsing Apple’s XML with no standard library and possible format changes.
- One pipeline (PDF + .docx) is simpler to build and maintain.

**Libraries:**

- **PDF:** `pypdf` or `PyMuPDF` (fitz) for text extraction. For scanned/image PDFs, add `pdf2image` + `pytesseract` (OCR) later if needed.
- **.docx:** `python-docx` — extract paragraphs/runs as plain text.

**Implementation prompt (for ingest-from-files):**

- Accept a path or list of paths (PDF and/or .docx).
- Per file: extract full text (and optionally title/source from filename or metadata).
- Call existing POST /ingest with that `text` (and metadata) so chunk → embed → store runs as already designed.

---

## Models (local, for client-name privacy)

- **Text RAG:** **Qwen3 8B** (or `LLM_MODEL`, default `qwen3:8b`) via Ollama for POST /ask. Run with `ollama run qwen3:8b`; point LLM client at `LLM_BASE_URL` (e.g. `http://localhost:11434`).
- **Image → report text:** Vision model via Ollama for POST /ask/image and POST /ingest/image. Same base URL (`LLM_BASE_URL`); model name from `LLAVA_MODEL` (default `llava:7b`). Vision API: one image (file upload or URL) + optional prompt → model returns report-style or extracted text. No RAG for /ask/image. Pull with `ollama pull llava:7b`.

---

## Placeholder for future notes

- Chunking strategy for reports (by section? by chars?)
- Ledgerly-specific system prompt for POST /ask
- Any env vars or config for embed/LLM (see Models above)
