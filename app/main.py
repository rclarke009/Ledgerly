## 8. POST /ingest

# Wire the ingest endpoint: validate the request body with your Pydantic model;
#  chunk the `text` with your chunking function; insert one row into the documents
#  table; insert one row per chunk into the chunks table (build chunk id from docid:chunkindex); call your embedder for all
#  chunk texts; insert one row per chunk into the embeddings table; return your 
# ingest response. Decide and document: if `doc_id` already exists, do you return
#  an error (e.g. 409) or overwrite? If embedding fails after you’ve written 
# documents/chunks, do you roll back or leave partial data? Prefer “reject duplicate
#  doc_id” and “roll back or don’t persist on embed failure” so the DB stays 
# consistent.

# **Why now:** This is the first end-to-end flow: text in, chunks and embeddings 
# stored. Getting it right here makes the rest of the app usable.

# **Hint:** You can use a single transaction (begin, insert doc + chunks + embeddings,
#  commit) and roll back on any failure, or explicitly delete the document and its 
# chunks if embedding fails. Document your choice in a comment or in `code-notes.md`.

## 9. POST /ask

# Wire the ask endpoint: validate the request; embed the question with the same embedder 
# you use for chunks; call your retrieval function to get top-k chunks; build a prompt 
# that includes a short system instruction (e.g. “You suggest report wording based on 
# the following context”), the user’s question, and a “Context:” section with the 
# retrieved chunks (include doc_id and maybe chunk_id so the model can refer to sources). 
# Call your LLM with that prompt and return the model’s answer plus the list of top chunks 
# (and optionally scores/snippets). Cap the total context length (e.g. character or token
#  limit) so you don’t exceed model limits. If retrieval returns no chunks, either return 
# a message like “I don’t have relevant context” or call the LLM without context and say 
# so in the prompt.

# **Why now:** This completes the RAG loop: question → embed → retrieve → prompt 
# with context → LLM → answer. Ledgerly’s value is “ask for overview/detail wording 
# and get it from similar reports.”

# **Hint:** Reuse your ai-document LLM client or a minimal async caller; point it at 
# **Ollama** (e.g. `http://localhost:11434`) and use **Qwen3 8B** (`qwen3:8b`, `LLM_MODEL`) 
# so all generation stays local for client-name privacy. Keep the prompt template in 
# one place so you can tune it later for “overview and detailed image wording.” 
# Vision: **LLAVA_MODEL** on Ollama for “look at this job’s images and write report text.”

## 10. GET /documents (list ingested)

# Add an endpoint that returns a list of what has already been ingested so users can 
# see what’s in the system (confirm uploads, spot duplicates, scan by title). Implement
#  **GET /documents** (or **GET /ingest** if you prefer) that queries the documents table
#  and returns a list of items. Each item should include at least: `doc_id`, `title`, 
# `source`, `created_at`, and `num_chunks`. Optionally include a short `snippet` (e.g. 
# first 200–300 characters of the document text, or of the first chunk’s content) so users
#  get a quick preview. Define a Pydantic response model (e.g. `DocumentSummary` with those
#  fields) and a list response (e.g. `DocumentsListResponse` with `documents: 
# list[DocumentSummary]`). Add a DB helper that selects from `documents` and optionally 
# joins with the first chunk per doc for the snippet; keep the query simple (e.g. order 
# by `created_at` desc).


import base64
import hashlib
import os
import platform
import subprocess
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import unquote, urlparse
from typing import Any, Awaitable, Callable
import uuid

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse, StreamingResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
import sqlite3
import asyncio
import time
import logging
import json
import mimetypes

from app.db import (
    create_db,
    delete_by_doc_id,
    delete_document_cascade,
    get_doc_ids_by_tag,
    insert_chunk,
    insert_document,
    insert_embedding,
    set_document_tags,
    set_document_linked_account,
    doc_exist,
    find_doc_id_by_content_hash,
    list_documents,
    list_accounts,
    list_positions,
    list_obligations,
    get_position,
    get_obligation,
    get_account,
    insert_account,
    update_account,
    delete_account,
    insert_position,
    update_position,
    delete_position,
    insert_obligation,
    update_obligation,
    delete_obligation,
    insert_decision_history,
    list_decision_history,
    list_trigger_events,
    get_document_source,
    get_document_original_vault_path,
    update_document_source,
    get_positions_by_document_id,
    get_obligations_by_document_id,
    set_document_extracted_position,
    clear_document_extracted_position,
    set_document_extracted_obligation,
    clear_document_extracted_obligation,
    list_documents_with_extracted_obligation,
    resolve_position,
    resolve_obligation,
    insert_ira_overview,
    list_ira_overview,
    get_ira_overview,
    update_ira_overview,
    delete_ira_overview,
)
from app.models import (
    AskGeneralRequest,
    AskGeneralResponse,
    AskImageResponse,
    AskRequest,
    AskResponse,
    ChunkingOptions,
    DocumentSummary,
    DocumentUpdateRequest,
    DocumentsListResponse,
    IngestRequest,
    IngestResponse,
    IngestEnqueueResponse,
    IngestJobEnqueueItem,
    IngestJobStatusResponse,
    AskJobEnqueueResponse,
    AskJobStatusResponse,
    IngestGoogleDriveRequest,
    IngestGoogleDriveResponse,
    DecisionResponse,
    TriggerEventResponse,
    UserDataSource,
    WebSource,
    DecisionHistoryItem,
    AskHistoryItem,
    DashboardResponse,
    ConfirmExtractionRequest,
    ConfirmExtractionResponse,
    ConfirmObligationExtractionRequest,
    ConfirmObligationExtractionResponse,
    ExtractedPosition,
    ExtractedObligation,
    ResolvePositionRequest,
    ResolveObligationRequest,
    AccountCreate,
    AccountUpdate,
    AccountResponse,
    PositionCreate,
    PositionUpdate,
    PositionResponse,
    ObligationCreate,
    ObligationUpdate,
    ObligationResponse,
    IraOverviewCreate,
    IraOverviewUpdate,
    IraOverviewResponse,
    VaultStatusResponse,
    VaultPendingIngestRequest,
    VaultSettingsGetResponse,
    VaultSettingsConfigAllowedResponse,
    VaultSettingsPutRequest,
    VaultRootVerifyRequest,
    VaultRootVerifyResponse,
    VaultNativePickFolderResponse,
    VaultIncomingScanResponse,
    WarmupResponse,
    WarmupStatusResponse,
)
from app.triggers import evaluate_triggers
from app.dashboard import build_dashboard
from app.extraction_apply import apply_obligation_extraction, apply_position_extraction
from app.ingest_structured import (
    detect_tax_document_tags,
    extract_structured_obligation,
    extract_structured_position,
)
from app.reference_data import fetch_cd_rates_with_cache, RateInfo
from app.decision_memo import (
    build_action_summary_memo,
    build_maturity_memo_sections,
    build_no_action_memo,
    build_openai_maturity_prompt,
)
from app.config import MATURITY_DAYS_AHEAD, OBLIGATION_DAYS_AHEAD
from app.rate_limit import TokenBucket
from app.chunking import chunk_text_chars
from app.embeddings import HttpEmbedder
from app.job_store import JobStore
from app.worker import worker_loop
from app.ingest_queue import IngestJobStore
from app.ingest_worker import ingest_worker_loop
from app.ingest_jobs import IngestJob, IngestJobKind
from app.pdf_ingest import parse_pdf_text_mode, resolve_pdf_for_ingest
from app.ask_graph import build_prompt_and_chunks
from app.ask_history import fetch_ask_history, fetch_conversation, insert_complete_answer, insert_pending_for_job
from app.ask_queue import AskJobStore
from app.ask_worker import ask_worker_loop
from app.ask_jobs import AskJob
from app.answer_format import (
    ANSWER_FORMAT_PROMPT_SUFFIX,
    merge_structured_to_response,
    normalize_markdown_layout,
    split_structured,
)
from app.advice_format import split_advice_bullets
from app.retrieval import retrieve_top_k
from app.reranker import rerank
from app.errors import LLMRateLimitedError, LLMServiceError, LLMTimeoutError, LLMUpstreamTimeoutError
from app.drive_client import list_and_export_docs, DriveClientError
from app.config import (
    DATABASE_URL,
    DB_PATH,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
    INGEST_FACTS_ENABLED,
    INGEST_STRUCTURED_ENABLED,
    INGEST_AUTO_TRACK_ENABLED,
    METRICS_ENABLED,
    RERANK_ENABLED,
    RERANK_INITIAL_K_MAX,
    RERANK_INITIAL_K_MULTIPLIER,
    ALLOW_REMOTE_VAULT_SETTINGS,
    VAULT_SAVE_TEXT_INGEST,
    ASK_COOLDOWN_AFTER_PREP_SEC,
    ASK_QUEUE_ESTIMATED_WAIT_SEC,
    _portable_profile,
)
from app import originals_vault as originals_vault_mod
from app.vault_settings_store import (
    effective_vault_root_source,
    file_settings_snapshot,
    resolve_vault_incoming_mode,
    resolve_vault_root,
    vault_root_is_from_env,
    write_vault_settings_file,
)
from app.vault_path_validation import validate_vault_root_path
from app.native_folder_dialog import NativeFolderDialogUnavailable, pick_native_folder
from app.db_connection import app_db_connection
from app import llm_client
from app.ingest_facts import extract_document_facts
from app.remote_log import send_remote_log
from app.ask_trace import AskTraceContext, ask_trace_scope, log_ask_event
from app.api_errors import error_envelope, http_error_code
from app.ollama_warmup import get_warmup_status, request_warmup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class DuplicateContentError(Exception):
    """Raised when the same text/PDF content is already ingested (same content_hash)."""
    def __init__(self, existing_doc_id: str):
        self.existing_doc_id = existing_doc_id
        super().__init__(f"Content already ingested as doc_id={existing_doc_id!r}")


@asynccontextmanager
async def lifespan(app):
    if DATABASE_URL:
        import psycopg

        app.state.use_postgres = True
        app.state.pg_dsn = DATABASE_URL
        app.state.db_path = ""
        with psycopg.connect(DATABASE_URL) as init_conn:
            create_db(init_conn)
            init_conn.commit()
        logger.info("Database: Postgres (DATABASE_URL)")
    else:
        app.state.use_postgres = False
        app.state.pg_dsn = None
        app.state.db_path = DB_PATH
        newdb = sqlite3.connect(app.state.db_path)
        create_db(newdb)
        newdb.close()
        logger.info("Database: SQLite at %s", app.state.db_path)

    app.state.job_store = JobStore()
    job_store = app.state.job_store

    app.state.ingest_job_store = IngestJobStore()
    app.state.ask_job_store = AskJobStore()

    #create token bucket
    app.state.rate_limiter = TokenBucket()
    rate_limiter = app.state.rate_limiter

    #create task loop - worker will poll for pending jobs and process them.
    task = asyncio.create_task(worker_loop(job_store, rate_limiter))
    ingest_worker_task = asyncio.create_task(ingest_worker_loop(app))
    ask_worker_task = asyncio.create_task(ask_worker_loop(app))
    vault_watch_task: asyncio.Task | None = None
    try:
        if originals_vault_mod.vault_enabled() and originals_vault_mod.vault_watcher_requested():
            from app.vault_watcher import vault_watcher_loop

            vault_watch_task = asyncio.create_task(vault_watcher_loop(app))
    except Exception as e:
        logger.warning("Vault watcher not started: %s", e)
    app.state.vault_watch_task = vault_watch_task
    logger.info("Work Started")

    yield
    task.cancel()
    ingest_worker_task.cancel()
    ask_worker_task.cancel()
    vwt_shutdown = getattr(app.state, "vault_watch_task", None)
    if vwt_shutdown is not None:
        vwt_shutdown.cancel()

    try:
        await task
    except asyncio.CancelledError as e:
        pass
    try:
        await ingest_worker_task
    except asyncio.CancelledError:
        pass
    try:
        await ask_worker_task
    except asyncio.CancelledError:
        pass
    if vwt_shutdown is not None:
        try:
            await vwt_shutdown
        except asyncio.CancelledError:
            pass

    logger.info("Work has stopped")


def _request_may_configure_vault(request: Request) -> bool:
    if ALLOW_REMOTE_VAULT_SETTINGS:
        return True
    client = request.client
    return _client_host_is_loopback(client.host if client else None)


async def restart_vault_watcher_app(app: Any) -> None:
    from app.vault_watcher import vault_watcher_loop

    old = getattr(app.state, "vault_watch_task", None)
    if old is not None and not old.done():
        old.cancel()
        try:
            await old
        except asyncio.CancelledError:
            pass
    app.state.vault_watch_task = None
    if originals_vault_mod.vault_enabled() and originals_vault_mod.vault_watcher_requested():
        app.state.vault_watch_task = asyncio.create_task(vault_watcher_loop(app))


# create the web service and async life cycle thingy
app = FastAPI(
    title="Ledgerly",
    description="Private cash and document assistant API",
    lifespan=lifespan,
)

if METRICS_ENABLED:
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator(
        should_ignore_untemplated=True,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/metrics"],
    ).instrument(app).expose(app, include_in_schema=False)


@app.middleware("http")
async def request_id_and_duration_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    request.state.trace_id = request_id
    request.state.start_time = time.perf_counter()
    request.state.route = f"{request.method} {request.url.path}"
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


def _duration_ms(request: Request) -> int | None:
    if not getattr(request.state, "start_time", None):
        return None
    return int((time.perf_counter() - request.state.start_time) * 1000)


def _ask_trace_from_request(request: Request, question: str) -> AskTraceContext:
    q = (question or "").strip()
    preview = q[:80] + ("…" if len(q) > 80 else "")
    rid = getattr(request.state, "request_id", None) or "unknown"
    http_route = getattr(request.state, "route", None) or f"{request.method} {request.url.path}"
    return AskTraceContext(request_id=str(rid), http_route=http_route, question_preview=preview)


def _log_ask_begin(body: AskRequest) -> None:
    log_ask_event(
        "ask_begin",
        top_k=body.top_k,
        use_rag=body.use_rag,
        doc_id_set=bool(body.doc_id and str(body.doc_id).strip()),
        doc_ids_count=len(body.doc_ids or []),
        tag_set=bool(body.tag and str(body.tag).strip()),
        question_len=len(body.question or ""),
    )


def _strip_nul_bytes(s: str) -> str:
    """PostgreSQL text columns reject NUL (0x00); PDF extractors sometimes emit them."""
    return s.replace("\x00", "")


def _document_summary_from_row(r: tuple[Any, ...]) -> DocumentSummary:
    """Map list_documents row tuple to DocumentSummary (10 fields when original_vault_path present)."""
    vault_rel = r[9] if len(r) > 9 else None
    return DocumentSummary(
        doc_id=r[0],
        title=r[1],
        source=r[2],
        created_at=r[3],
        num_chunks=r[4],
        snippet=r[5],
        tags=r[6] if len(r) > 6 else [],
        linked_account_ids=r[7] if len(r) > 7 else [],
        facts_learned=r[8] if len(r) > 8 else None,
        original_vault_path=vault_rel,
        has_openable_original=_stored_original_file_exists(r[2], vault_rel),
    )
def _remote_log_error(request: Request, message: str, error_type: str) -> None:
    send_remote_log(
        level="ERROR",
        message=message,
        route=getattr(request.state, "route", None),
        request_id=getattr(request.state, "request_id", None),
        trace_id=getattr(request.state, "trace_id", None),
        duration_ms=_duration_ms(request),
        error_type=error_type,
    )


async def ingest_text(
    conn: Any,
    doc_id: str,
    title: str | None,
    source: str | None,
    text: str,
    chunking_options: ChunkingOptions,
    confirm_duplicate_content: bool = False,
    tags: list[str] | None = None,
    account_id: str | None = None,
    progress: Callable[..., Awaitable[None]] | None = None,
    *,
    vault_original: tuple[str, bytes] | None = None,
    vault_text_utf8_snapshot: bytes | None = None,
    persist_normalized_text_snapshot: bool = True,
    canonical_original_vault_rel: str | None = None,
) -> IngestResponse:
    """
    Shared ingest: chunk text, insert document + chunks, embed, insert embeddings, commit.
    Raises ValueError('doc_id already exists') if doc_id is duplicate.
    Raises DuplicateContentError(existing_doc_id) if same content already ingested and not confirmed.
    Rollback (delete_by_doc_id) on embedding failure.
    Optional progress(stage, progress_pct) for queued ingests (0–100).
    """
    async def _maybe_progress(stage: str, pct: float, **kwargs: Any) -> None:
        if progress is not None:
            await progress(stage, pct, **kwargs)

    if doc_exist(conn, doc_id):
        raise ValueError("doc_id already exists")
    if title is not None:
        title = _strip_nul_bytes(title)
    if source is not None:
        source = _strip_nul_bytes(source)
    normalized = _strip_nul_bytes(text.strip())
    content_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    if not confirm_duplicate_content:
        existing_doc_id = find_doc_id_by_content_hash(conn, content_hash)
        if existing_doc_id is not None:
            raise DuplicateContentError(existing_doc_id)
    opts = chunking_options
    chunks = chunk_text_chars(normalized, opts.chunk_size, opts.chunk_overlap)
    await _maybe_progress("chunking", 15.0)
    facts_learned_json: str | None = None
    facts_for_response: list[str] | None = None
    if INGEST_FACTS_ENABLED:
        await _maybe_progress("facts", 16.0)
        try:
            facts_list = await extract_document_facts(normalized, title)
            if facts_list:
                facts_learned_json = json.dumps(facts_list)
                facts_for_response = facts_list
        except Exception as e:
            logger.warning("ingest facts: skipped due to error: %s", e)
    effective_source = source
    stored_vault_rel: str | None = None
    text_snapshot = vault_text_utf8_snapshot
    if (
        vault_original is None
        and text_snapshot is None
        and canonical_original_vault_rel is None
        and originals_vault_mod.vault_enabled()
        and VAULT_SAVE_TEXT_INGEST
        and persist_normalized_text_snapshot
    ):
        text_snapshot = normalized.encode("utf-8")
    if canonical_original_vault_rel:
        stored_vault_rel = canonical_original_vault_rel
        p_canon = originals_vault_mod.absolute_from_vault_relative(canonical_original_vault_rel)
        if p_canon is not None:
            effective_source = str(p_canon)
    elif originals_vault_mod.vault_enabled() and vault_original is not None:
        rel, abs_saved = originals_vault_mod.save_original(
            doc_id, vault_original[0], vault_original[1]
        )
        if rel is not None:
            stored_vault_rel = rel
        if abs_saved is not None:
            effective_source = str(abs_saved)
    elif originals_vault_mod.vault_enabled() and text_snapshot is not None:
        rel, abs_saved = originals_vault_mod.save_text_snapshot(doc_id, text_snapshot)
        if rel is not None:
            stored_vault_rel = rel
        if abs_saved is not None:
            effective_source = str(abs_saved)

    insert_document(
        conn,
        doc_id,
        int(time.time()),
        title,
        effective_source,
        content_hash=content_hash,
        facts_learned=facts_learned_json,
        original_vault_path=stored_vault_rel,
    )
    for chunk in chunks:
        chunk_id = f"{doc_id}:{chunk.chunk_index}"
        insert_chunk(
            conn, chunk_id, doc_id, chunk.chunk_index, chunk.content,
            chunk.start_offset, chunk.end_offset,
        )
    await _maybe_progress("embedding", 20.0)
    embedder = HttpEmbedder()

    async def _on_embed_batch(batch_idx: int, total_batches: int) -> None:
        if progress is None:
            return
        pct = 20.0 + (batch_idx / max(total_batches, 1)) * 70.0
        await progress(
            "embedding",
            min(pct, 89.9),
            batches_done=batch_idx,
            total_embed_batches=total_batches,
        )

    try:
        vectors = await embedder.embed_many(
            [c.content for c in chunks],
            on_embed_batch_complete=_on_embed_batch if progress else None,
        )
    except Exception as e:
        delete_by_doc_id(conn, doc_id)
        conn.commit()
        logger.exception("embedding failed", exc_info=e)
        raise
    await _maybe_progress("saving", 92.0)
    for chunk, vector in zip(chunks, vectors):
        chunk_id = f"{doc_id}:{chunk.chunk_index}"
        insert_embedding(conn, chunk_id, embedder.model, json.dumps(vector), embedder.dim)
    if tags:
        set_document_tags(conn, doc_id, tags)
    tax_tags = detect_tax_document_tags(title, normalized)
    if tax_tags:
        merged_tags = list(dict.fromkeys((tags or []) + tax_tags))
        set_document_tags(conn, doc_id, merged_tags)
    if account_id:
        set_document_linked_account(conn, doc_id, account_id)
    extracted_for_response: ExtractedPosition | None = None
    extracted_obligation_for_response: ExtractedObligation | None = None
    if INGEST_STRUCTURED_ENABLED:
        await _maybe_progress("structured", 90.0)
        try:
            extracted_dict = await extract_structured_position(normalized, title)
            if extracted_dict and extracted_dict.get("maturity_date"):
                set_document_extracted_position(conn, doc_id, json.dumps(extracted_dict))
                extracted_for_response = ExtractedPosition(**extracted_dict)
        except Exception as e:
            logger.warning("ingest structured: skipped due to error: %s", e)
        if extracted_for_response is None:
            try:
                obl_dict = await extract_structured_obligation(normalized, title)
                if obl_dict and obl_dict.get("due_date"):
                    set_document_extracted_obligation(conn, doc_id, json.dumps(obl_dict))
                    extracted_obligation_for_response = ExtractedObligation(**obl_dict)
            except Exception as e:
                logger.warning("ingest obligation structured: skipped due to error: %s", e)

    auto_tracked_position = None
    auto_tracked_obligation = None
    if INGEST_AUTO_TRACK_ENABLED:
        try:
            if extracted_for_response is not None:
                auto_tracked_position = apply_position_extraction(
                    conn, doc_id, extracted=extracted_for_response
                )
            elif extracted_obligation_for_response is not None:
                auto_tracked_obligation = apply_obligation_extraction(
                    conn, doc_id, extracted=extracted_obligation_for_response
                )
        except Exception as e:
            logger.warning("auto-track on ingest failed for %s: %s", doc_id, e)

    conn.commit()
    has_openable_original = _stored_original_file_exists(effective_source, stored_vault_rel)
    return IngestResponse(
        doc_id=doc_id,
        num_chunks=len(chunks),
        embedding_model=embedder.model,
        dim=embedder.dim,
        facts_learned=facts_for_response,
        extracted_position=extracted_for_response,
        extracted_obligation=extracted_obligation_for_response,
        auto_tracked_position=auto_tracked_position,
        auto_tracked_obligation=auto_tracked_obligation,
        source=effective_source,
        original_vault_path=stored_vault_rel,
        has_openable_original=has_openable_original,
    )


@app.post("/ingest", response_model=IngestResponse)
async def ingest(request: Request, ingest_request: IngestRequest):
    with app_db_connection(request.app) as conn:
        try:
            return await ingest_text(
                conn,
                ingest_request.doc_id,
                ingest_request.title,
                ingest_request.source,
                ingest_request.text,
                ingest_request.chunking_options,
                confirm_duplicate_content=ingest_request.confirm_duplicate_content,
                tags=ingest_request.tags or None,
                account_id=ingest_request.account_id,
            )
        except DuplicateContentError as e:
            raise HTTPException(
                status_code=409,
                detail={"code": "duplicate_content", "existing_doc_id": e.existing_doc_id},
            ) from e
        except ValueError as e:
            if "already exists" in str(e):
                raise HTTPException(
                    status_code=409,
                    detail="A document with this ID already exists. Use a different document ID or delete the existing document first.",
                ) from e
            raise
        except Exception as e:
            logger.exception("POST /ingest failed")
            raise HTTPException(status_code=503, detail="Embedding failed") from e


@app.post("/ingest/pdf", response_model=IngestResponse)
async def ingest_pdf(request: Request):
    """
    Ingest a PDF file: multipart/form-data with required 'file' (PDF),
    optional doc_id, title, source, chunk_size, chunk_overlap.
    Extracts text server-side (native text when strong; otherwise OCR / vision per server policy) then chunk/embed.
    """
    form = await request.form()
    file = form.get("file")
    if file is None or not hasattr(file, "read"):
        raise HTTPException(
            status_code=400,
            detail="multipart form must include 'file' (PDF).",
        )
    raw = await file.read()
    if len(raw) > INGEST_PDF_MAX_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"PDF too large (max {INGEST_PDF_MAX_BYTES // (1024*1024)} MB).",
        )
    if not raw.startswith(PDF_MAGIC):
        raise HTTPException(
            status_code=400,
            detail="File does not appear to be a PDF.",
        )
    try:
        pdf_mode_raw = form.get("pdf_text_mode")
        pdf_mode = parse_pdf_text_mode(pdf_mode_raw if isinstance(pdf_mode_raw, str) else None)
        text = await resolve_pdf_for_ingest(raw, pdf_mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("PDF extraction failed", exc_info=e)
        raise HTTPException(
            status_code=400,
            detail=f"Failed to read PDF: {e!s}",
        ) from e
    text = (text or "").strip()
    if not text:
        raise HTTPException(
            status_code=400,
            detail="No text could be extracted from this PDF.",
        )
    filename = getattr(file, "filename", None) or "upload.pdf"
    doc_id_raw = form.get("doc_id")
    doc_id = str(doc_id_raw).strip() if isinstance(doc_id_raw, str) else None
    if not doc_id:
        doc_id = str(uuid.uuid4())
    title_raw = form.get("title")
    title = str(title_raw).strip() or None if isinstance(title_raw, str) else None
    source_raw = form.get("source")
    source = (str(source_raw).strip() or filename) if isinstance(source_raw, str) else filename
    chunk_size = 800
    chunk_overlap = 100
    cs = form.get("chunk_size")
    if cs is not None:
        try:
            chunk_size = int(cs) if isinstance(cs, str) else int(cs)
        except (TypeError, ValueError):
            pass
    co = form.get("chunk_overlap")
    if co is not None:
        try:
            chunk_overlap = int(co) if isinstance(co, str) else int(co)
        except (TypeError, ValueError):
            pass
    try:
        chunking_options = ChunkingOptions(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    confirm_duplicate = form.get("confirm_duplicate_content")
    confirm_duplicate_content = str(confirm_duplicate).strip().lower() in ("1", "true", "yes")
    tags_raw = form.get("tags")
    tags_list = None
    if tags_raw is not None and isinstance(tags_raw, str) and tags_raw.strip():
        tags_list = [t.strip() for t in tags_raw.split(",") if t.strip()]
    account_id_raw = form.get("account_id")
    account_id = str(account_id_raw).strip() or None if isinstance(account_id_raw, str) else None
    with app_db_connection(request.app) as conn:
        try:
            return await ingest_text(
                conn, doc_id, title, source, text, chunking_options,
                confirm_duplicate_content=confirm_duplicate_content,
                tags=tags_list,
                account_id=account_id,
                vault_original=(filename, raw),
                persist_normalized_text_snapshot=False,
            )
        except DuplicateContentError as e:
            raise HTTPException(
                status_code=409,
                detail={"code": "duplicate_content", "existing_doc_id": e.existing_doc_id},
            ) from e
        except ValueError as e:
            if "already exists" in str(e):
                raise HTTPException(
                    status_code=409,
                    detail="A document with this ID already exists. Use a different document ID or delete the existing document first.",
                ) from e
            raise
        except Exception as e:
            logger.exception("POST /ingest/pdf failed")
            raise HTTPException(status_code=503, detail="Embedding failed") from e


def _is_supported_image(data: bytes) -> bool:
    """True if data looks like JPEG or PNG (magic bytes)."""
    return data.startswith(JPEG_MAGIC) or data.startswith(PNG_MAGIC)


@app.post("/ingest/image", response_model=IngestResponse)
async def ingest_image(request: Request):
    """
    Ingest an image file (JPG or PNG): multipart/form-data with required 'file',
    optional doc_id, title, source, chunk_size, chunk_overlap.
    Uses LLaVA to extract visible text (e.g. from bank screenshots), then runs
    the same chunk/embed pipeline as POST /ingest.
    """
    form = await request.form()
    file = form.get("file")
    if file is None or not hasattr(file, "read"):
        raise HTTPException(
            status_code=400,
            detail="multipart form must include 'file' (image).",
        )
    raw = await file.read()
    if len(raw) > INGEST_IMAGE_MAX_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Image too large (max {INGEST_IMAGE_MAX_BYTES // (1024*1024)} MB).",
        )
    if not _is_supported_image(raw):
        raise HTTPException(
            status_code=400,
            detail="File must be a JPEG or PNG image.",
        )
    try:
        image_base64 = base64.b64encode(raw).decode("ascii")
        filename = getattr(file, "filename", None) or "upload.jpg"
        text = await llm_client.image_to_text_for_ingest(image_base64, filename_hint=filename)
    except (LLMServiceError, LLMRateLimitedError, LLMUpstreamTimeoutError) as e:
        logger.exception("Image text extraction failed", exc_info=e)
        raise HTTPException(status_code=503, detail=str(e)) from e
    text = (text or "").strip()
    if len(text) < 10:
        raise HTTPException(
            status_code=400,
            detail="No text could be extracted from the image.",
        )
    doc_id_raw = form.get("doc_id")
    doc_id = str(doc_id_raw).strip() if isinstance(doc_id_raw, str) else None
    if not doc_id:
        doc_id = str(uuid.uuid4())
    title_raw = form.get("title")
    title = str(title_raw).strip() or None if isinstance(title_raw, str) else None
    source_raw = form.get("source")
    source = (str(source_raw).strip() or filename) if isinstance(source_raw, str) else filename
    chunk_size = 800
    chunk_overlap = 100
    cs = form.get("chunk_size")
    if cs is not None:
        try:
            chunk_size = int(cs) if isinstance(cs, str) else int(cs)
        except (TypeError, ValueError):
            pass
    co = form.get("chunk_overlap")
    if co is not None:
        try:
            chunk_overlap = int(co) if isinstance(co, str) else int(co)
        except (TypeError, ValueError):
            pass
    try:
        chunking_options = ChunkingOptions(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    confirm_duplicate = form.get("confirm_duplicate_content")
    confirm_duplicate_content = str(confirm_duplicate).strip().lower() in ("1", "true", "yes")
    tags_raw = form.get("tags")
    tags_list = None
    if tags_raw is not None and isinstance(tags_raw, str) and tags_raw.strip():
        tags_list = [t.strip() for t in tags_raw.split(",") if t.strip()]
    account_id_raw = form.get("account_id")
    account_id = str(account_id_raw).strip() or None if isinstance(account_id_raw, str) else None
    with app_db_connection(request.app) as conn:
        try:
            return await ingest_text(
                conn, doc_id, title, source, text, chunking_options,
                confirm_duplicate_content=confirm_duplicate_content,
                tags=tags_list,
                account_id=account_id,
                vault_original=(filename, raw),
                persist_normalized_text_snapshot=False,
            )
        except DuplicateContentError as e:
            raise HTTPException(
                status_code=409,
                detail={"code": "duplicate_content", "existing_doc_id": e.existing_doc_id},
            ) from e
        except ValueError as e:
            if "already exists" in str(e):
                raise HTTPException(
                    status_code=409,
                    detail="A document with this ID already exists. Use a different document ID or delete the existing document first.",
                ) from e
            raise
        except Exception as e:
            logger.exception("POST /ingest/image failed")
            raise HTTPException(status_code=503, detail="Embedding failed") from e


def _ingest_job_to_response(job: IngestJob) -> IngestJobStatusResponse:
    return IngestJobStatusResponse(
        id=job.id,
        status=job.status.value,
        kind=job.kind.value,
        filename=job.filename,
        created_at=job.created_at,
        updated_at=job.updated_at,
        progress_pct=job.progress_pct,
        stage=job.stage,
        eta_seconds=job.eta_seconds,
        estimated_completion_at=job.estimated_completion_at,
        error=job.error,
        result=job.result,
    )


@app.post("/ingest/jobs", response_model=IngestEnqueueResponse, status_code=202)
async def ingest_jobs_enqueue(request: Request):
    """
    Queue one or more PDFs or images for background ingest (FIFO, one at a time).
    Returns job ids immediately; poll GET /ingest/jobs/{id} for progress.
    """
    form = await request.form()
    uploads = form.getlist("file")
    if not uploads:
        raise HTTPException(
            status_code=400,
            detail="multipart form must include one or more 'file' fields.",
        )

    doc_id_raw = form.get("doc_id")
    form_doc_id = str(doc_id_raw).strip() if isinstance(doc_id_raw, str) else None
    title_raw = form.get("title")
    title = str(title_raw).strip() or None if isinstance(title_raw, str) else None
    source_raw = form.get("source")
    chunk_size = 800
    chunk_overlap = 100
    cs = form.get("chunk_size")
    if cs is not None:
        try:
            chunk_size = int(cs) if isinstance(cs, str) else int(cs)
        except (TypeError, ValueError):
            pass
    co = form.get("chunk_overlap")
    if co is not None:
        try:
            chunk_overlap = int(co) if isinstance(co, str) else int(co)
        except (TypeError, ValueError):
            pass
    try:
        ChunkingOptions(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    confirm_duplicate = form.get("confirm_duplicate_content")
    confirm_duplicate_content = str(confirm_duplicate).strip().lower() in ("1", "true", "yes")
    tags_raw = form.get("tags")
    tags_list = None
    if tags_raw is not None and isinstance(tags_raw, str) and tags_raw.strip():
        tags_list = [t.strip() for t in tags_raw.split(",") if t.strip()]
    account_id_raw = form.get("account_id")
    account_id = str(account_id_raw).strip() or None if isinstance(account_id_raw, str) else None
    pdf_mode_raw = form.get("pdf_text_mode")
    try:
        pdf_text_mode = parse_pdf_text_mode(pdf_mode_raw if isinstance(pdf_mode_raw, str) else None).value
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    store: IngestJobStore = request.app.state.ingest_job_store
    out: list[IngestJobEnqueueItem] = []
    multi = len(uploads) > 1

    for upload in uploads:
        if upload is None or not hasattr(upload, "read"):
            continue
        raw = await upload.read()
        filename = getattr(upload, "filename", None) or "upload"
        if raw.startswith(PDF_MAGIC):
            if len(raw) > INGEST_PDF_MAX_BYTES:
                raise HTTPException(
                    status_code=400,
                    detail=f"PDF too large (max {INGEST_PDF_MAX_BYTES // (1024*1024)} MB): {filename}",
                )
            kind = IngestJobKind.PDF
        elif _is_supported_image(raw):
            if len(raw) > INGEST_IMAGE_MAX_BYTES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Image too large (max {INGEST_IMAGE_MAX_BYTES // (1024*1024)} MB): {filename}",
                )
            kind = IngestJobKind.IMAGE
        else:
            raise HTTPException(
                status_code=400,
                detail=f"File must be PDF or JPEG/PNG: {filename}",
            )

        suffix = Path(filename).suffix if filename else ""
        fd, tmp_path = tempfile.mkstemp(prefix="ingestq_", suffix=suffix or ".bin")
        try:
            os.write(fd, raw)
        finally:
            os.close(fd)

        if multi:
            doc_id = str(uuid.uuid4())
        else:
            doc_id = (form_doc_id or "").strip() or str(uuid.uuid4())

        source = (str(source_raw).strip() or filename) if isinstance(source_raw, str) else filename

        job = IngestJob(
            id=uuid.uuid4().hex,
            kind=kind,
            filename=filename,
            temp_path=tmp_path,
            doc_id=doc_id,
            title=title,
            source=source,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            confirm_duplicate_content=confirm_duplicate_content,
            tags=tags_list,
            account_id=account_id,
            pdf_text_mode=pdf_text_mode,
        )
        await store.add(job)
        out.append(IngestJobEnqueueItem(job_id=job.id, filename=filename))

    if not out:
        raise HTTPException(status_code=400, detail="No valid files in request.")
    return IngestEnqueueResponse(jobs=out)


@app.get("/ingest/jobs/{job_id}", response_model=IngestJobStatusResponse)
async def get_ingest_job(request: Request, job_id: str):
    store: IngestJobStore = request.app.state.ingest_job_store
    job = await store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _ingest_job_to_response(job)


@app.get("/ingest/jobs", response_model=list[IngestJobStatusResponse])
async def list_ingest_jobs(request: Request, ids: str | None = None, limit: int = 50):
    store: IngestJobStore = request.app.state.ingest_job_store
    if ids:
        id_list = [x.strip() for x in ids.split(",") if x.strip()]
        jobs = await store.list_ids(id_list)
    else:
        jobs = await store.list_recent(min(limit, 200))
    return [_ingest_job_to_response(j) for j in jobs]


@app.post("/ingest/google-drive", response_model=IngestGoogleDriveResponse)
async def ingest_google_drive(request: Request, body: IngestGoogleDriveRequest):
    """
    Ingest Google Docs from Drive (read-only). List/export then run shared ingest per doc.
    Duplicate doc_id is skipped and counted; other errors are recorded and processing continues.
    """
    try:
        docs = list_and_export_docs(folder_id=body.folder_id, file_ids=body.file_ids)
    except DriveClientError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    default_opts = ChunkingOptions()
    ingested = 0
    skipped = 0
    errors: list[str] = []
    doc_ids: list[str] = []
    with app_db_connection(request.app) as conn:
        for doc in docs:
            try:
                await ingest_text(
                    conn,
                    doc.doc_id,
                    doc.title,
                    doc.source,
                    doc.text,
                    default_opts,
                    persist_normalized_text_snapshot=False,
                )
                ingested += 1
                doc_ids.append(doc.doc_id)
            except ValueError as e:
                if "already exists" in str(e):
                    skipped += 1
                else:
                    errors.append(f"{doc.doc_id} ({doc.title}): {e}")
            except Exception as e:
                errors.append(f"{doc.doc_id} ({doc.title}): {e}")
                logger.warning("Ingest failed for %s: %s", doc.doc_id, e)
    return IngestGoogleDriveResponse(
        ingested=ingested,
        skipped=skipped,
        errors=errors,
        doc_ids=doc_ids,
    )


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _ask_meta_payload(
    *,
    conversation_id: str | None = None,
    turn_id: str | None = None,
    related_documents: list | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    if turn_id:
        payload["turn_id"] = turn_id
    if related_documents:
        payload["related_documents"] = [
            d.model_dump() if hasattr(d, "model_dump") else d for d in related_documents
        ]
    return payload


def _ask_response_extras(turn_result, related_documents) -> dict[str, Any]:
    return {
        "conversation_id": turn_result.conversation_id,
        "turn_id": turn_result.turn_id,
        "related_documents": related_documents or [],
    }


@app.post("/ask", response_model=AskResponse)
async def ask(request: Request, ask_request: AskRequest):
    """RAG over documents plus optional Layer 2 (your data) summary so user can ask about CDs, obligations, etc."""
    await _check_ingest_busy(request)
    t0 = time.perf_counter()
    trace_ctx = _ask_trace_from_request(request, ask_request.question)
    with ask_trace_scope(trace_ctx):
        _log_ask_begin(ask_request)
        with app_db_connection(request.app) as conn:
            rate_limiter = request.app.state.rate_limiter
            t_build = time.perf_counter()
            messages, top_chunks, route, has_context, direct_answer, related_documents = (
                await build_prompt_and_chunks(conn, ask_request)
            )
            build_ms = _elapsed_ms(t_build)
            logger.info(
                "Ask: graph build done in %d ms route=%s chunks=%d",
                build_ms,
                route,
                len(top_chunks),
            )
            if not has_context:
                total_ms = _elapsed_ms(t0)
                logger.info("Ask: early return (no context) total=%d ms", total_ms)
                log_ask_event(
                    "ask_early_exit",
                    reason="no_context",
                    graph_route=route,
                    top_chunks=len(top_chunks),
                    total_ms=total_ms,
                )
                no_ctx_msg = "I don't have relevant context or data to answer that question."
                turn_result = insert_complete_answer(
                    conn,
                    ask_request,
                    no_ctx_msg,
                    route=route,
                    related_documents=related_documents,
                    top_chunks=top_chunks,
                )
                return AskResponse(
                    answer=no_ctx_msg,
                    top_chunks=[],
                    tables=[],
                    charts=[],
                    **_ask_response_extras(turn_result, related_documents),
                )

            if direct_answer:
                total_ms = _elapsed_ms(t0)
                logger.info("Ask: fast path in %d ms route=%s", total_ms, route)
                answer_msg = normalize_markdown_layout(direct_answer)
                turn_result = insert_complete_answer(
                    conn,
                    ask_request,
                    answer_msg,
                    route=route,
                    related_documents=related_documents,
                    top_chunks=top_chunks,
                )
                return AskResponse(
                    answer=answer_msg,
                    top_chunks=top_chunks,
                    tables=[],
                    charts=[],
                    **_ask_response_extras(turn_result, related_documents),
                )

            t3 = time.perf_counter()
            await rate_limiter.acquire()
            rate_limit_ms = _elapsed_ms(t3)
            if rate_limit_ms > 0:
                logger.info("Ask: rate limit wait %d ms", rate_limit_ms)

            t4 = time.perf_counter()
            raw_answer = await llm_client.answer_with_messages(messages)
            body, tail = split_structured(raw_answer)
            answer, tables, charts = merge_structured_to_response(body, tail)
            answer = normalize_markdown_layout(answer)
            llm_ms = _elapsed_ms(t4)
            total_ms = _elapsed_ms(t0)
            logger.info(
                "Ask: LLM done in %d ms | total=%d ms (build=%d rate_limit=%d llm=%d)",
                llm_ms,
                total_ms,
                build_ms,
                rate_limit_ms,
                llm_ms,
            )
            turn_result = insert_complete_answer(
                conn,
                ask_request,
                answer,
                tables=[t.model_dump() for t in tables],
                charts=[c.model_dump() for c in charts],
                route=route,
                related_documents=related_documents,
                top_chunks=top_chunks,
            )
            return AskResponse(
                answer=answer,
                top_chunks=top_chunks,
                tables=tables,
                charts=charts,
                **_ask_response_extras(turn_result, related_documents),
            )


def _is_portable_profile() -> bool:
    return _portable_profile() in ("portable", "low_spec")


def _ask_job_to_response(job: AskJob) -> AskJobStatusResponse:
    return AskJobStatusResponse(
        id=job.id,
        status=job.status.value if hasattr(job.status, "value") else str(job.status),
        stage=job.stage,
        progress_pct=job.progress_pct,
        eta_seconds=job.eta_seconds,
        error=job.error,
        answer=job.answer,
        route=job.route,
        top_chunks=job.top_chunks,
        tables=job.tables,
        charts=job.charts,
        conversation_id=job.conversation_id,
        turn_id=job.turn_id,
        related_documents=job.related_documents,
    )


async def _check_ingest_busy(request: Request) -> None:
    if not _is_portable_profile():
        return
    store: IngestJobStore = request.app.state.ingest_job_store
    if await store.has_running_job():
        raise HTTPException(
            status_code=503,
            detail=(
                "Document processing is running. Wait for ingest to finish, "
                "or use background Ask (queued mode) instead."
            ),
        )


def _structured_payload(answer: str, tables=None, charts=None) -> dict[str, Any]:
    return {
        "answer": answer,
        "tables": [t.model_dump() for t in (tables or [])],
        "charts": [c.model_dump() for c in (charts or [])],
    }


async def _stream_direct_answer(
    answer: str,
    top_chunks: list | None = None,
    *,
    conversation_id: str | None = None,
    turn_id: str | None = None,
    related_documents: list | None = None,
):
    msg = normalize_markdown_layout(answer)
    structured = _structured_payload(msg, [], [])
    yield json.dumps({"phase": "done"}) + "\n"
    payload: dict[str, Any] = {
        "top_chunks": top_chunks or [],
        "answer": msg,
        "structured": structured,
        "done": True,
    }
    payload.update(
        _ask_meta_payload(
            conversation_id=conversation_id,
            turn_id=turn_id,
            related_documents=related_documents,
        )
    )
    yield json.dumps(payload) + "\n"


async def _stream_ask_full(
    request: Request,
    ask_request: AskRequest,
    trace_ctx: AskTraceContext,
    stream_start_time: float,
):
    """NDJSON stream: phases during build, then chunks/deltas/structured/done."""
    phase_queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def progress_cb(stage: str) -> None:
        await phase_queue.put(stage)

    build_result: list[Any] = []

    async def run_build():
        with app_db_connection(request.app) as conn:
            build_result.append(
                await build_prompt_and_chunks(conn, ask_request, progress_cb=progress_cb)
            )
        await phase_queue.put(None)

    yield json.dumps({"phase": "routing"}) + "\n"
    build_task = asyncio.create_task(run_build())

    while True:
        if build_task.done() and phase_queue.empty():
            break
        try:
            phase = await asyncio.wait_for(phase_queue.get(), timeout=0.25)
        except asyncio.TimeoutError:
            continue
        if phase is None:
            break
        yield json.dumps({"phase": phase}) + "\n"

    if build_task is not None:
        await build_task

    messages, top_chunks, route, has_context, direct_answer, related_documents = build_result[0]
    build_ms = _elapsed_ms(stream_start_time)
    logger.info(
        "Ask/stream: graph build done in %d ms route=%s chunks=%d",
        build_ms,
        route,
        len(top_chunks),
    )

    if not has_context:
        msg = "I don't have relevant context or data to answer that question."
        with app_db_connection(request.app) as conn:
            turn_result = insert_complete_answer(
                conn,
                ask_request,
                msg,
                route=route,
                related_documents=related_documents,
                top_chunks=top_chunks,
            )
        async for line in _stream_direct_answer(
            msg,
            [],
            conversation_id=turn_result.conversation_id,
            turn_id=turn_result.turn_id,
            related_documents=related_documents,
        ):
            yield line
        return

    meta = {
        "top_chunks": [c.model_dump() if hasattr(c, "model_dump") else c for c in top_chunks],
        **_ask_meta_payload(related_documents=related_documents),
    }
    yield json.dumps(meta) + "\n"

    if direct_answer:
        answer_msg = normalize_markdown_layout(direct_answer)
        with app_db_connection(request.app) as conn:
            turn_result = insert_complete_answer(
                conn,
                ask_request,
                answer_msg,
                route=route,
                related_documents=related_documents,
                top_chunks=top_chunks,
            )
        async for line in _stream_direct_answer(
            direct_answer,
            meta["top_chunks"],
            conversation_id=turn_result.conversation_id,
            turn_id=turn_result.turn_id,
            related_documents=related_documents,
        ):
            yield line
        return

    rate_limiter = request.app.state.rate_limiter
    await rate_limiter.acquire()
    if ASK_COOLDOWN_AFTER_PREP_SEC > 0:
        await asyncio.sleep(ASK_COOLDOWN_AFTER_PREP_SEC)

    yield json.dumps({"phase": "generating"}) + "\n"
    stream_result: list[tuple[str, list, list]] = []
    async for line in _stream_ask_generator(
        messages,
        top_chunks,
        stream_start_time=stream_start_time,
        trace_ctx=trace_ctx,
        skip_meta=True,
        stream_result=stream_result,
        related_documents=related_documents,
    ):
        yield line
    if stream_result:
        answer, tables, charts = stream_result[0]
        with app_db_connection(request.app) as conn:
            turn_result = insert_complete_answer(
                conn,
                ask_request,
                answer,
                tables=tables,
                charts=charts,
                route=route,
                related_documents=related_documents,
                top_chunks=top_chunks,
            )
        tail = _ask_meta_payload(
            conversation_id=turn_result.conversation_id,
            turn_id=turn_result.turn_id,
            related_documents=related_documents,
        )
        payload: dict[str, Any] = {"done": True}
        payload.update(tail)
        yield json.dumps(payload) + "\n"


async def _stream_ask_generator(
    messages: list[dict[str, str]],
    top_chunks: list,
    stream_start_time: float | None = None,
    trace_ctx: AskTraceContext | None = None,
    *,
    skip_meta: bool = False,
    stream_result: list[tuple[str, list, list]] | None = None,
    related_documents: list | None = None,
):
    """Yield NDJSON lines: optional top_chunks, then deltas from LLM, then structured, then done."""
    t0 = stream_start_time if stream_start_time is not None else time.perf_counter()
    t_llm_start = time.perf_counter()
    logger.info("Ask/stream: generator started, LLM stream starting")
    if not skip_meta:
        meta = {
            "top_chunks": [c.model_dump() if hasattr(c, "model_dump") else c for c in top_chunks],
            **_ask_meta_payload(related_documents=related_documents),
        }
        yield json.dumps(meta) + "\n"
    first_delta = True
    accumulated = ""

    try:
        if trace_ctx is not None:
            with ask_trace_scope(trace_ctx):
                async for delta in llm_client.answer_with_messages_stream(messages):
                    accumulated += delta
                    if first_delta:
                        first_delta_ms = _elapsed_ms(t_llm_start)
                        logger.info("Ask/stream: first LLM delta in %d ms", first_delta_ms)
                        first_delta = False
                    yield json.dumps({"delta": delta}) + "\n"
        else:
            async for delta in llm_client.answer_with_messages_stream(messages):
                accumulated += delta
                if first_delta:
                    first_delta_ms = _elapsed_ms(t_llm_start)
                    logger.info("Ask/stream: first LLM delta in %d ms", first_delta_ms)
                    first_delta = False
                yield json.dumps({"delta": delta}) + "\n"
    except Exception as e:
        logger.exception("Ask/stream: LLM stream failed")
        llm_ms = _elapsed_ms(t_llm_start)
        total_ms = _elapsed_ms(t0)
        logger.info("Ask/stream: LLM stream failed after %d ms, total=%d ms", llm_ms, total_ms)
        rid = trace_ctx.request_id if trace_ctx else None
        if isinstance(e, httpx.ConnectError):
            detail = (
                "Cannot reach the AI backend. It may still be starting or offline. "
                "Ask the administrator to check Ledgerly logs or Docker/Ollama."
            )
            code = "upstream_connect"
        elif isinstance(e, httpx.ConnectTimeout):
            detail = (
                "Timed out connecting to the AI backend. If this persists, the administrator "
                "should verify Ollama is running and reachable from Ledgerly."
            )
            code = "upstream_connect"
        elif isinstance(e, httpx.ReadTimeout):
            detail = (
                "The AI backend took too long to respond. Wait and try again, or ask "
                "the administrator to check model load or increase timeouts."
            )
            code = "llm_timeout"
        elif isinstance(e, httpx.TimeoutException):
            detail = (
                "The AI backend did not respond in time. Ask the administrator to check "
                "Ledgerly and Ollama status."
            )
            code = "llm_timeout"
        elif isinstance(e, LLMServiceError):
            detail = str(e).strip() or "The AI backend returned an error."
            code = "llm_service"
        elif isinstance(e, LLMRateLimitedError):
            detail = "Too many assistant requests too quickly. Wait a minute and try again."
            code = "rate_limit"
        else:
            detail = (
                "The assistant could not finish streaming this answer. "
                "If it keeps happening, contact the person who runs Ledgerly."
            )
            code = "llm_stream_failed"
        err_line: dict[str, Any] = {"error": detail, "code": code, "done": True}
        if rid:
            err_line["request_id"] = rid
        yield json.dumps(err_line) + "\n"
        return
    llm_ms = _elapsed_ms(t_llm_start)
    total_ms = _elapsed_ms(t0)
    logger.info("Ask/stream: LLM stream done in %d ms, total=%d ms", llm_ms, total_ms)
    body, tail = split_structured(accumulated)
    answer, tables, charts = merge_structured_to_response(body, tail)
    answer = normalize_markdown_layout(answer)
    if stream_result is not None:
        stream_result.append(
            (
                answer,
                [t.model_dump() for t in tables],
                [c.model_dump() for c in charts],
            )
        )
    structured = {
        "answer": answer,
        "tables": [t.model_dump() for t in tables],
        "charts": [c.model_dump() for c in charts],
    }
    yield json.dumps({"structured": structured}) + "\n"
    # Final done line with conversation metadata is emitted by _stream_ask_full after history insert.


@app.post("/ask/stream")
async def ask_stream(request: Request, ask_request: AskRequest):
    """RAG same as /ask but streams NDJSON with phase progress, chunks, deltas, structured, done."""
    await _check_ingest_busy(request)
    t0 = time.perf_counter()
    question_preview = (ask_request.question or "")[:80]
    trace_ctx = _ask_trace_from_request(request, ask_request.question)
    with ask_trace_scope(trace_ctx):
        _log_ask_begin(ask_request)
        logger.info("Ask/stream: start question=%s", question_preview)

        async def body():
            with ask_trace_scope(trace_ctx):
                async for line in _stream_ask_full(request, ask_request, trace_ctx, t0):
                    yield line

        return StreamingResponse(body(), media_type="application/x-ndjson")


@app.post("/ask/jobs", response_model=AskJobEnqueueResponse, status_code=202)
async def ask_jobs_enqueue(request: Request, ask_request: AskRequest):
    """Queue a question for background processing (one at a time, paced for CPU)."""
    await _check_ingest_busy(request)
    import time as _time

    store: AskJobStore = request.app.state.ask_job_store
    job = AskJob(
        id=uuid.uuid4().hex,
        question=ask_request.question.strip(),
        top_k=ask_request.top_k,
        doc_id=ask_request.doc_id,
        tag=ask_request.tag,
        use_rag=ask_request.use_rag,
        conversation_id=ask_request.conversation_id,
        eta_seconds=ASK_QUEUE_ESTIMATED_WAIT_SEC,
        created_at=_time.time(),
    )
    pending = await store.pending_count()
    est = ASK_QUEUE_ESTIMATED_WAIT_SEC + pending * 120
    job.eta_seconds = est
    await store.add(job)
    with app_db_connection(request.app) as conn:
        turn_result = insert_pending_for_job(conn, job.id, ask_request, asked_at=job.created_at)
        job.conversation_id = turn_result.conversation_id
        job.turn_id = turn_result.turn_id
    return AskJobEnqueueResponse(job_id=job.id, estimated_wait_sec=est)


@app.get("/ask/history", response_model=list[AskHistoryItem])
def get_ask_history(request: Request, limit: int = 50):
    """List recent Ask Ledgerly questions and answers."""
    with app_db_connection(request.app) as conn:
        return fetch_ask_history(conn, limit=limit)


@app.get("/ask/conversations/{conversation_id}", response_model=list[AskHistoryItem])
def get_ask_conversation(request: Request, conversation_id: str):
    """Load all turns in an Ask conversation thread."""
    with app_db_connection(request.app) as conn:
        turns = fetch_conversation(conn, conversation_id)
        if not turns:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return turns


@app.get("/ask/jobs/{job_id}", response_model=AskJobStatusResponse)
async def get_ask_job(request: Request, job_id: str):
    store: AskJobStore = request.app.state.ask_job_store
    job = await store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Ask job not found")
    return _ask_job_to_response(job)


@app.get("/ask/jobs", response_model=list[AskJobStatusResponse])
async def list_ask_jobs(request: Request, limit: int = 20):
    store: AskJobStore = request.app.state.ask_job_store
    jobs = await store.list_recent(limit=limit)
    return [_ask_job_to_response(j) for j in jobs]


# Max image size for POST /ask/image (file upload or URL fetch)
ASK_IMAGE_MAX_BYTES = 10 * 1024 * 1024  # 10 MB

# Max PDF size for POST /ingest/pdf
INGEST_PDF_MAX_BYTES = 20 * 1024 * 1024  # 20 MB

# PDF magic bytes (simplified: %PDF)
PDF_MAGIC = b"%PDF"

# Image magic bytes for POST /ingest/image
JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
INGEST_IMAGE_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


@app.post("/ask/image", response_model=AskImageResponse)
async def ask_image(request: Request):
    """
    Image → report text via LLaVA (Ollama vision). No RAG.
    Accept either:
    - JSON: {"image_url": "https://...", "prompt": "optional"}
    - multipart/form-data: image=<file>, prompt=<optional>
    """
    rate_limiter = request.app.state.rate_limiter
    content_type = (request.headers.get("content-type") or "").lower()
    prompt = "Describe this image and summarize any financial details or terms."
    image_base64: str | None = None

    if "application/json" in content_type:
        body = await request.json()
        image_url = body.get("image_url")
        if not image_url or not isinstance(image_url, str):
            raise HTTPException(
                status_code=400,
                detail="JSON body must include 'image_url' (string).",
            )
        prompt = (body.get("prompt") or prompt).strip() or prompt
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(image_url)
                resp.raise_for_status()
                raw = resp.content
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to fetch image from URL: {e!s}",
            ) from e
        if len(raw) > ASK_IMAGE_MAX_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"Image too large (max {ASK_IMAGE_MAX_BYTES // (1024*1024)} MB).",
            )
        image_base64 = base64.b64encode(raw).decode("ascii")
    else:
        form = await request.form()
        file = form.get("image")
        if file is None or not hasattr(file, "read"):
            raise HTTPException(
                status_code=400,
                detail="multipart form must include 'image' file.",
            )
        raw = await file.read()
        if len(raw) > ASK_IMAGE_MAX_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"Image too large (max {ASK_IMAGE_MAX_BYTES // (1024*1024)} MB).",
            )
        p = form.get("prompt")
        if isinstance(p, str) and p.strip():
            prompt = p.strip()
        image_base64 = base64.b64encode(raw).decode("ascii")

    if not image_base64:
        raise HTTPException(status_code=400, detail="No image provided.")
    await rate_limiter.acquire()
    answer = await llm_client.answer_with_image(image_base64, prompt)
    return AskImageResponse(answer=answer)


@app.post("/ask/general", response_model=AskGeneralResponse)
async def ask_general(request: Request, body: AskGeneralRequest):
    """
    General-path only: templated or custom prompts sent to OpenAI. No RAG, no user documents.
    Use template + optional amount/term_months for CD templates, or template=custom + question.
    """
    trace_q = (body.question or "") if body.template == "custom" else f"template:{body.template}"
    trace_ctx = _ask_trace_from_request(request, trace_q)
    with ask_trace_scope(trace_ctx):
        log_ask_event(
            "ask_general_begin",
            template=body.template,
            amount_set=body.amount is not None,
            term_months_set=body.term_months is not None,
            question_len=len(body.question or ""),
        )
        rate_limiter = request.app.state.rate_limiter
        logger.info(
            "Ask/general: start template=%s amount=%s term_months=%s",
            body.template,
            body.amount,
            body.term_months,
        )
        if body.template == "custom" and body.question:
            logger.info(
                "Ask/general: custom question preview=%s",
                body.question[:80] + ("…" if len(body.question) > 80 else ""),
            )
        if body.template == "cd_rates_summary":
            prompt = "Summarize the current US CD rate environment in 2-3 sentences." + ANSWER_FORMAT_PROMPT_SUFFIX
        elif body.template == "cd_advice":
            amount_str = f"${body.amount:,.0f}" if body.amount is not None else "an amount"
            term_str = f" {body.term_months}-month" if body.term_months is not None else ""
            prompt = (
                f"What should someone do if they have {amount_str} in a{term_str} CD maturing now? "
                "Give 2-3 short options."
            ) + ANSWER_FORMAT_PROMPT_SUFFIX
        elif body.template == "custom":
            # Validated by AskGeneralRequest: non-empty question for custom.
            q = body.question or ""
            prompt = (
                "You are a concise financial education assistant. Answer clearly and briefly. "
                "Do not provide personalized investment, tax, or legal advice; give general information only. "
                "If the question is not finance-related, answer helpfully in a short way.\n\n"
                "Question:\n"
                + q
            ) + ANSWER_FORMAT_PROMPT_SUFFIX
        else:
            raise HTTPException(status_code=400, detail="Unknown template")
        logger.info("Ask/general: prompt length=%d chars", len(prompt))
        await rate_limiter.acquire()
        raw_answer = await llm_client.answer_openai(prompt)
        logger.info("Ask/general: done answer_length=%s", len(raw_answer) if raw_answer else 0)
        if raw_answer is None:
            raise HTTPException(
                status_code=503,
                detail="OpenAI not configured (set OPENAI_API_KEY for general-path advice).",
            )
        resp_body, tail = split_structured(raw_answer)
        answer, tables, charts = merge_structured_to_response(resp_body, tail)
        answer = normalize_markdown_layout(answer)
        return AskGeneralResponse(answer=answer, tables=tables, charts=charts)


@app.get("/documents", response_model=DocumentsListResponse)
def get_documents(request: Request):
    with app_db_connection(request.app) as conn:
        rows = list_documents(conn)
        documents = [_document_summary_from_row(r) for r in rows]
        return DocumentsListResponse(documents=documents)


@app.get("/vault/status", response_model=VaultStatusResponse)
def get_vault_status() -> VaultStatusResponse:
    if not originals_vault_mod.vault_enabled():
        return VaultStatusResponse(
            enabled=False,
            watcher_mode=resolve_vault_incoming_mode(),
            root=None,
            writable=None,
            originals_dir=None,
            incoming_dir=None,
            pending_dir=None,
            root_source=None,
        )
    r = originals_vault_mod.vault_root()
    wr = originals_vault_mod.vault_writable()
    o, inc, pend = originals_vault_mod.originals_dir(), originals_vault_mod.incoming_dir(), originals_vault_mod.pending_dir()
    originals_vault_mod.ensure_vault_layout()
    return VaultStatusResponse(
        enabled=True,
        watcher_mode=resolve_vault_incoming_mode(),
        root=str(r) if r else None,
        writable=wr,
        originals_dir=str(o) if o else None,
        incoming_dir=str(inc) if inc else None,
        pending_dir=str(pend) if pend else None,
        root_source=effective_vault_root_source(),
    )


@app.get("/vault/settings/config-allowed", response_model=VaultSettingsConfigAllowedResponse)
def get_vault_settings_config_allowed(request: Request) -> VaultSettingsConfigAllowedResponse:
    return VaultSettingsConfigAllowedResponse(allowed=_request_may_configure_vault(request))


@app.get("/vault/settings", response_model=VaultSettingsGetResponse)
def get_vault_settings() -> VaultSettingsGetResponse:
    snap = file_settings_snapshot()
    eff_root = resolve_vault_root()
    mode = resolve_vault_incoming_mode()
    env_ctl = vault_root_is_from_env()
    fr = str(snap.get("root", "")).strip() if snap else None
    if not fr:
        fr = None
    fm = snap.get("incoming_mode") if snap else None
    fm_s = str(fm).strip().lower() if fm is not None else None
    if fm_s not in ("off", "watch_auto", "watch_review"):
        fm_s = None
    wr = originals_vault_mod.vault_writable() if eff_root else None
    o = inc_dir = pnd = None
    if eff_root:
        originals_vault_mod.ensure_vault_layout()
        od, idir, pd = (
            originals_vault_mod.originals_dir(),
            originals_vault_mod.incoming_dir(),
            originals_vault_mod.pending_dir(),
        )
        o = str(od) if od else None
        inc_dir = str(idir) if idir else None
        pnd = str(pd) if pd else None
    return VaultSettingsGetResponse(
        effective_root=str(eff_root) if eff_root else None,
        effective_incoming_mode=mode,
        root_source=effective_vault_root_source(),
        file_root=fr,
        file_incoming_mode=fm_s,
        writable=wr,
        originals_dir=o,
        incoming_dir=inc_dir,
        pending_dir=pnd,
        env_controls_settings=env_ctl,
    )


@app.put("/vault/settings", response_model=VaultSettingsGetResponse)
async def put_vault_settings(request: Request, body: VaultSettingsPutRequest) -> VaultSettingsGetResponse:
    if not _request_may_configure_vault(request):
        raise HTTPException(
            status_code=403,
            detail="Vault settings can be changed from localhost or set ALLOW_REMOTE_VAULT_SETTINGS=true.",
        )
    if vault_root_is_from_env():
        raise HTTPException(
            status_code=400,
            detail="Vault root is set via LEDGERLY_ORIGINALS_VAULT; unset it to use saved settings from the UI.",
        )
    m = body.incoming_mode.strip().lower()
    if m not in ("off", "watch_auto", "watch_review"):
        raise HTTPException(status_code=400, detail="incoming_mode must be off, watch_auto, or watch_review")
    if "root" in body.model_fields_set:
        root_str = (body.root or "").strip()
    else:
        snap = file_settings_snapshot() or {}
        root_str = str(snap.get("root") or "").strip()
    if root_str:
        vr = validate_vault_root_path(root_str)
        if not vr.valid:
            raise HTTPException(status_code=400, detail=vr.detail or "Invalid vault directory")
        write_root = vr.resolved_root or ""
    else:
        write_root = ""
    write_vault_settings_file(write_root if write_root else None, m)
    await restart_vault_watcher_app(request.app)
    return get_vault_settings()


@app.post("/vault/settings/verify-root", response_model=VaultRootVerifyResponse)
def post_vault_settings_verify_root(request: Request, body: VaultRootVerifyRequest) -> VaultRootVerifyResponse:
    if not _request_may_configure_vault(request):
        raise HTTPException(
            status_code=403,
            detail="Vault settings can be changed from localhost or set ALLOW_REMOTE_VAULT_SETTINGS=true.",
        )
    if vault_root_is_from_env():
        raise HTTPException(
            status_code=400,
            detail="Vault root is set via LEDGERLY_ORIGINALS_VAULT; unset it to use saved settings from the UI.",
        )
    vr = validate_vault_root_path(body.root)
    return VaultRootVerifyResponse(
        valid=vr.valid,
        resolved_root=vr.resolved_root,
        incoming_dir=vr.incoming_dir,
        pending_dir=vr.pending_dir,
        originals_dir=vr.originals_dir,
        detail=vr.detail,
    )


@app.post("/vault/settings/native-pick-folder", response_model=VaultNativePickFolderResponse)
async def post_vault_settings_native_pick_folder(request: Request) -> VaultNativePickFolderResponse:
    client = request.client
    if not _client_host_is_loopback(client.host if client else None):
        raise HTTPException(
            status_code=403,
            detail="Native folder picker is only allowed from localhost.",
        )
    if vault_root_is_from_env():
        raise HTTPException(
            status_code=400,
            detail="Vault root is set via LEDGERLY_ORIGINALS_VAULT; unset it to use saved settings from the UI.",
        )
    try:
        result = await asyncio.to_thread(pick_native_folder)
    except NativeFolderDialogUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return VaultNativePickFolderResponse(path=result.path, cancelled=result.cancelled)


@app.get("/vault/pending", response_model=list[str])
def list_vault_pending() -> list[str]:
    """List files under vault/pending/ (watch_review) as relative POSIX paths (nested dirs included)."""
    if not originals_vault_mod.vault_enabled():
        raise HTTPException(status_code=400, detail="LEDGERLY_ORIGINALS_VAULT is not set")
    from app.vault_pathutil import list_pending_relative_paths

    return list_pending_relative_paths()


@app.post("/vault/pending/ingest", response_model=IngestJobEnqueueItem, status_code=202)
async def ingest_vault_pending_by_path(
    request: Request, body: VaultPendingIngestRequest
) -> IngestJobEnqueueItem:
    """Enqueue ingest for a file under pending/ by relative path (supports subfolders)."""
    if not originals_vault_mod.vault_enabled():
        raise HTTPException(status_code=400, detail="LEDGERLY_ORIGINALS_VAULT is not set")
    from app.vault_pathutil import enqueue_raw_as_ingest_job, resolve_pending_relative_path

    dest = resolve_pending_relative_path(body.relative_path)
    if dest is None:
        raise HTTPException(status_code=404, detail="File not found in vault pending/")
    raw = dest.read_bytes()
    rel_norm = body.relative_path.strip().replace("\\", "/").lstrip("/")
    store = request.app.state.ingest_job_store
    keep_rel = f"{originals_vault_mod.REL_PENDING}/{rel_norm}"
    jid, err = await enqueue_raw_as_ingest_job(
        store,
        raw,
        rel_norm,
        remove_source_after=None,
        keep_incoming_original_rel=keep_rel,
    )
    if err or not jid:
        raise HTTPException(status_code=400, detail=err or "Could not enqueue ingest job")
    return IngestJobEnqueueItem(job_id=jid, filename=rel_norm)


@app.post("/vault/pending/{filename}/ingest", response_model=IngestJobEnqueueItem, status_code=202)
async def ingest_vault_pending_file(request: Request, filename: str) -> IngestJobEnqueueItem:
    if not originals_vault_mod.vault_enabled():
        raise HTTPException(status_code=400, detail="LEDGERLY_ORIGINALS_VAULT is not set")
    from app.vault_pathutil import enqueue_raw_as_ingest_job, safe_pending_destination

    _, dest = safe_pending_destination(filename)
    if dest is None or not dest.is_file():
        raise HTTPException(status_code=404, detail="File not found in vault pending/")
    raw = dest.read_bytes()
    store = request.app.state.ingest_job_store
    pd = originals_vault_mod.pending_dir()
    if pd is None:
        raise HTTPException(status_code=400, detail="Vault pending/ not available")
    rel_pending = dest.relative_to(pd.resolve()).as_posix()
    keep_rel = f"{originals_vault_mod.REL_PENDING}/{rel_pending}"
    jid, err = await enqueue_raw_as_ingest_job(
        store,
        raw,
        rel_pending,
        remove_source_after=None,
        keep_incoming_original_rel=keep_rel,
    )
    if err or not jid:
        raise HTTPException(status_code=400, detail=err or "Could not enqueue ingest job")
    return IngestJobEnqueueItem(job_id=jid, filename=rel_pending)


_VAULT_SCAN_SUFFIXES = frozenset({".pdf", ".png", ".jpg", ".jpeg"})


@app.post("/vault/incoming/scan", response_model=VaultIncomingScanResponse)
async def vault_incoming_scan(request: Request) -> VaultIncomingScanResponse:
    if not _request_may_configure_vault(request):
        raise HTTPException(
            status_code=403,
            detail="Scan allowed from localhost or ALLOW_REMOTE_VAULT_SETTINGS=true.",
        )
    if not originals_vault_mod.vault_enabled():
        raise HTTPException(status_code=400, detail="Vault is not configured")
    from app.vault_pathutil import enqueue_raw_as_ingest_job
    from app.vault_watcher import move_incoming_file_to_pending

    mode = resolve_vault_incoming_mode()
    originals_vault_mod.ensure_vault_layout()
    incoming = originals_vault_mod.incoming_dir()
    pending = originals_vault_mod.pending_dir()
    if incoming is None or pending is None:
        raise HTTPException(status_code=400, detail="Vault directories not available")
    store = request.app.state.ingest_job_store
    enqueued = 0
    moved_to_pending = 0
    skipped = 0
    errors: list[str] = []

    incoming_r = incoming.resolve()
    pending_r = pending.resolve()
    for p in sorted(incoming_r.rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        try:
            rel = p.relative_to(incoming_r)
        except ValueError:
            continue
        if any(part.startswith(".") for part in rel.parts):
            skipped += 1
            continue
        suf = p.suffix.lower()
        if suf not in _VAULT_SCAN_SUFFIXES:
            skipped += 1
            continue
        if mode == "watch_review":
            moved = move_incoming_file_to_pending(p, rel, incoming_r, pending_r)
            if moved:
                moved_to_pending += 1
            else:
                errors.append(f"Could not move to pending: {rel.as_posix()}")
            continue
        try:
            raw = p.read_bytes()
        except OSError as e:
            errors.append(f"{rel.as_posix()}: {e}")
            continue
        incoming_rel = f"{originals_vault_mod.REL_INCOMING}/{rel.as_posix()}"
        display_name = rel.as_posix()
        jid, err = await enqueue_raw_as_ingest_job(
            store,
            raw,
            display_name,
            remove_source_after=None,
            keep_incoming_original_rel=incoming_rel,
        )
        if err or not jid:
            errors.append(f"{display_name}: {err or 'enqueue failed'}")
        else:
            enqueued += 1

    return VaultIncomingScanResponse(
        enqueued=enqueued,
        moved_to_pending=moved_to_pending,
        skipped=skipped,
        errors=errors[:50],
    )


def _client_host_is_loopback(host: str | None) -> bool:
    if not host:
        return False
    if host in ("127.0.0.1", "::1", "localhost", "testclient"):
        return True
    if host.startswith("127."):
        return True
    if host.startswith("::ffff:127."):
        return True
    return False


def _request_may_reveal_local_files(request: Request) -> bool:
    from app.config import ALLOW_LOCAL_FILE_REVEAL

    if ALLOW_LOCAL_FILE_REVEAL:
        return True
    client = request.client
    return _client_host_is_loopback(client.host if client else None)


def _stored_original_file_exists(
    effective_source: str | None, vault_rel: str | None
) -> bool:
    p = _path_from_document_source(effective_source)
    if p is None and vault_rel:
        p = originals_vault_mod.absolute_from_vault_relative(vault_rel)
    return p is not None and p.is_file()


def _path_from_document_source(raw: str | None) -> Path | None:
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    if s.lower().startswith("file:"):
        parsed = urlparse(s)
        path_str = unquote(parsed.path or "")
        if sys.platform == "win32" and len(path_str) >= 3 and path_str[0] == "/" and path_str[2] == ":":
            path_str = path_str[1:]
        p = Path(path_str)
    else:
        p = Path(s)
    if not p.is_absolute():
        return None
    return p


def _open_path_in_os(path: Path) -> None:
    resolved = path.resolve()
    s = str(resolved)
    system = platform.system()
    if system == "Darwin":
        subprocess.Popen(["open", s], close_fds=True)
    elif system == "Windows":
        os.startfile(s)
    else:
        subprocess.Popen(["xdg-open", s], close_fds=True)


def _resolve_document_original_file_path(conn: Any, doc_id: str) -> Path:
    if not doc_exist(conn, doc_id):
        raise HTTPException(status_code=404, detail="Document not found")
    raw = get_document_source(conn, doc_id)
    vault_rel = get_document_original_vault_path(conn, doc_id)
    p = _path_from_document_source(raw)
    if p is None and vault_rel:
        p = originals_vault_mod.absolute_from_vault_relative(vault_rel)
    if p is None:
        raise HTTPException(
            status_code=400,
            detail="Document has no usable absolute file path in source",
        )
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {p}")
    if not p.is_file():
        raise HTTPException(status_code=400, detail="Source path is not a file")
    return p


@app.post("/documents/{doc_id}/reveal-source")
def reveal_document_source(request: Request, doc_id: str):
    """Open the file at the stored absolute path (localhost or ALLOW_LOCAL_FILE_REVEAL only)."""
    if not _request_may_reveal_local_files(request):
        raise HTTPException(
            status_code=403,
            detail="Local file reveal is only allowed from localhost or when ALLOW_LOCAL_FILE_REVEAL=true",
        )
    with app_db_connection(request.app) as conn:
        p = _resolve_document_original_file_path(conn, doc_id)
    try:
        _open_path_in_os(p)
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return Response(status_code=204)


def _resolve_document_original_for_reveal(request: Request, doc_id: str) -> Path:
    """Resolve original path after localhost / ALLOW_LOCAL_FILE_REVEAL check."""
    if not _request_may_reveal_local_files(request):
        raise HTTPException(
            status_code=403,
            detail="Local file reveal is only allowed from localhost or when ALLOW_LOCAL_FILE_REVEAL=true",
        )
    with app_db_connection(request.app) as conn:
        return _resolve_document_original_file_path(conn, doc_id)


def _document_original_media_type(path: Path) -> str:
    mime_guess, _ = mimetypes.guess_type(path.name)
    return mime_guess or "application/octet-stream"


@app.head("/documents/{doc_id}/original")
def head_document_original(request: Request, doc_id: str):
    """Existence check for Preview prefetch (GET also works; HEAD is not auto-registered)."""
    p = _resolve_document_original_for_reveal(request, doc_id)
    media_type = _document_original_media_type(p)
    return Response(
        status_code=200,
        headers={
            "Content-Type": media_type,
            "Content-Length": str(p.stat().st_size),
        },
    )


@app.get("/documents/{doc_id}/original")
def serve_document_original(request: Request, doc_id: str):
    """Stream the original file (localhost or ALLOW_LOCAL_FILE_REVEAL only)."""
    p = _resolve_document_original_for_reveal(request, doc_id)
    media_type = _document_original_media_type(p)
    return FileResponse(path=str(p.resolve()), filename=p.name, media_type=media_type)


@app.patch("/documents/{doc_id}", response_model=DocumentSummary)
def patch_document(request: Request, doc_id: str, body: DocumentUpdateRequest):
    """Update document tags and/or linked account. Omit a field to leave it unchanged."""
    with app_db_connection(request.app) as conn:
        if not doc_exist(conn, doc_id):
            raise HTTPException(status_code=404, detail="Document not found")
        if "tags" in body.model_fields_set:
            set_document_tags(conn, doc_id, body.tags if body.tags is not None else [])
        if "account_id" in body.model_fields_set:
            set_document_linked_account(conn, doc_id, body.account_id)
        if "source" in body.model_fields_set:
            src = body.source
            if src is not None:
                src = _strip_nul_bytes(src)
                if src.strip() == "":
                    src = None
            update_document_source(conn, doc_id, src)
        conn.commit()
        rows = list_documents(conn)
        for r in rows:
            if r[0] == doc_id:
                return _document_summary_from_row(r)
    raise HTTPException(status_code=404, detail="Document not found")


@app.delete("/documents/{doc_id}", status_code=204)
def delete_document_route(request: Request, doc_id: str):
    """Delete document and cascade-remove linked positions and obligations."""
    with app_db_connection(request.app) as conn:
        if not doc_exist(conn, doc_id):
            raise HTTPException(status_code=404, detail="Document not found")
        delete_document_cascade(conn, doc_id)
        conn.commit()
    return None


def _build_data_summary(conn: Any, max_chars: int = 2000) -> str:
    """Build a short text summary of accounts, positions, obligations for Ask (data) context."""
    parts = []
    for row in list_accounts(conn):
        parts.append(f"Account: {row[1]} (type={row[2]}, institution={row[3]})")
    for row in list_positions(conn):
        pos_id, account_id, asset_type, desc, principal, rate_apr, maturity_date, doc_id, _, _ = row
        acc = get_account(conn, account_id)
        acc_name = acc[1] if acc else account_id
        line = f"Position: {asset_type}"
        if desc:
            line += f" {desc}"
        if principal is not None:
            line += f" principal={principal}"
        if rate_apr is not None:
            line += f" rate_apr={rate_apr}%"
        if maturity_date:
            line += f" maturity={maturity_date}"
        line += f" ({acc_name})"
        parts.append(line)
    for row in list_obligations(conn):
        obl_id, description, due_date, amount_estimate, priority, doc_id, _ = row
        line = f"Obligation: {description} due {due_date}"
        if amount_estimate is not None:
            line += f" amount_estimate={amount_estimate}"
        parts.append(line)
    s = "\n".join(parts) if parts else ""
    return s[:max_chars] + ("..." if len(s) > max_chars else "")


def _position_row_to_response(row: tuple) -> PositionResponse:
    return PositionResponse(
        id=row[0],
        account_id=row[1],
        asset_type=row[2],
        description=row[3],
        principal=row[4],
        rate_apr=row[5],
        maturity_date=row[6],
        document_id=row[7],
        created_at=row[8],
        updated_at=row[9],
        start_date=row[10] if len(row) > 10 else None,
        next_action=row[11] if len(row) > 11 else None,
        liquidity_note=row[12] if len(row) > 12 else None,
    )


def _ira_row_to_response(row: tuple) -> IraOverviewResponse:
    return IraOverviewResponse(
        id=row[0],
        account_name=row[1],
        institution=row[2],
        account_type=row[3],
        balance_estimate=row[4],
        rmd_note=row[5],
        next_relevant_date=row[6],
        document_id=row[7],
        created_at=row[8],
        updated_at=row[9],
    )


def _build_decision_sources(conn: Any, trigger_rows: list[tuple]) -> list[UserDataSource | WebSource]:
    """Build sources list: user data refs for entities in triggers, plus optional web refs added by caller."""
    sources: list[UserDataSource | WebSource] = []
    seen: set[tuple[str, str]] = set()
    for row in trigger_rows:
        _id, trigger_type, entity_type, entity_id, event_date, evaluated_at, status = row
        key = (entity_type, entity_id)
        if key in seen:
            continue
        seen.add(key)
        if entity_type == "position":
            pos = get_position(conn, entity_id)
            if pos:
                _, account_id, asset_type, desc, principal, rate_apr, maturity_date, doc_id, _, _ = pos
                acc = get_account(conn, account_id)
                acc_name = acc[1] if acc else account_id
                label = f"Position: {asset_type}"
                if desc:
                    label += f" {desc}"
                if maturity_date:
                    label += f", matures {maturity_date}"
                label += f" ({acc_name})"
                sources.append(UserDataSource(entity_type="position", id=entity_id, label=label))
        elif entity_type == "obligation":
            obl = get_obligation(conn, entity_id)
            if obl:
                _, description, due_date, amount_estimate, priority, doc_id, _ = obl
                label = f"Obligation: {description}, due {due_date}"
                sources.append(UserDataSource(entity_type="obligation", id=entity_id, label=label))
        elif entity_type == "ira_overview":
            ira = get_ira_overview(conn, entity_id)
            if ira:
                _, account_name, institution, account_type, _bal, _rmd, next_date, _doc, _, _ = ira
                label = f"IRA: {account_name}"
                if institution:
                    label += f" ({institution})"
                if next_date:
                    label += f", relevant date {next_date}"
                sources.append(UserDataSource(entity_type="ira_overview", id=entity_id, label=label))
    return sources


@app.get("/decision", response_model=DecisionResponse)
async def get_decision(request: Request):
    """
    Run trigger engine; return no_action_required or actionable with triggers, memo, and sources.
    Persists result to decision_history.
    """
    import uuid
    logger.info("Decision: start")
    with app_db_connection(request.app) as conn:
        triggers = evaluate_triggers(conn, persist=True)
        now_ts = int(time.time())
        logger.info("Decision: triggers evaluated count=%d", len(triggers))
        trigger_list = [
            TriggerEventResponse(
                id=r[0],
                trigger_type=r[1],
                entity_type=r[2],
                entity_id=r[3],
                event_date=r[4],
                evaluated_at=r[5],
                status=r[6],
            )
            for r in triggers
        ]
        sources = _build_decision_sources(conn, triggers)
        rate_infos: list[RateInfo] = []
        rate_comparisons: list[str] = []
        liquidity_notes: list[str] = []
        memo_sections: list[dict[str, Any]] = []

        if any(t[1] == "maturity" for t in triggers):
            try:
                rate_infos = await fetch_cd_rates_with_cache(conn)
                for ri in rate_infos[:4]:
                    sources.append(
                        WebSource(
                            quote=ri.quote,
                            url=ri.source_url,
                            source_name=ri.source_name,
                        )
                    )
            except Exception as e:
                logger.warning("Reference data fetch failed: %s", e)

        maturity_count = sum(1 for t in triggers if t[1] == "maturity" and t[2] == "position")
        logger.info("Decision: building memos for %d maturity trigger(s)", maturity_count)
        openai_advice: list[str] = []
        for t in triggers:
            if t[1] != "maturity" or t[2] != "position":
                continue
            section = build_maturity_memo_sections(conn, t[3], t[4], rate_infos)
            if not section:
                continue
            memo_sections.append(section)
            if section.get("rate_comparison", {}).get("summary"):
                rate_comparisons.append(section["rate_comparison"]["summary"])
            liq = section.get("liquidity") or {}
            if liq.get("summary"):
                liquidity_notes.append(liq["summary"])
            try:
                advice = await llm_client.answer_openai(build_openai_maturity_prompt(section))
                if advice:
                    for chunk in split_advice_bullets(advice):
                        openai_advice.append(chunk)
            except Exception as e:
                logger.warning("OpenAI advice for maturity trigger failed: %s", e)
                openai_advice.append(f"Recommendation: {section.get('recommendation', 'Review options')}")
                conf = section.get("confidence") or {}
                openai_advice.append(
                    f"Confidence: {conf.get('status', 'provisional')}; "
                    f"missing: {', '.join(conf.get('missing') or []) or 'none'}"
                )

        if not triggers:
            status = "no_action_required"
            memo = build_no_action_memo(conn)
            positions = list_positions(conn)
            obligations = list_obligations(conn)
            for row in positions[:10]:
                pos_id, account_id, asset_type, desc, principal, rate_apr, maturity_date, doc_id, _, _ = row[:10]
                acc = get_account(conn, account_id)
                acc_name = acc[1] if acc else account_id
                label = f"Position: {asset_type}" + (f" {desc}" if desc else "") + (f", matures {maturity_date}" if maturity_date else "") + f" ({acc_name})"
                sources.append(UserDataSource(entity_type="position", id=pos_id, label=label))
            for row in obligations[:10]:
                obl_id, description, due_date, amount_estimate, priority, doc_id, _ = row
                sources.append(UserDataSource(entity_type="obligation", id=obl_id, label=f"Obligation: {description}, due {due_date}"))
        else:
            status = "actionable"
            memo = build_action_summary_memo(len(triggers), memo_sections)
            if not memo_sections:
                days_label = max(MATURITY_DAYS_AHEAD, OBLIGATION_DAYS_AHEAD)
                memo = (
                    f"You have {len(triggers)} item(s) needing attention in the next {days_label} days. "
                    "Review maturity, obligation, and IRA awareness dates."
                )
        history_id = str(uuid.uuid4())
        trigger_ids_str = json.dumps([r[0] for r in triggers])
        insert_decision_history(conn, history_id, now_ts, status, memo, trigger_ids_str)
        conn.commit()
        logger.info(
            "Decision: done status=%s advice_count=%d rate_comparisons=%d",
            status,
            len(openai_advice),
            len(rate_comparisons),
        )
        return DecisionResponse(
            status=status,
            triggers=trigger_list,
            memo=memo,
            sources=sources,
            openai_advice=openai_advice,
            rate_comparisons=rate_comparisons,
            liquidity_notes=liquidity_notes,
        )


@app.get("/decision/history", response_model=list[DecisionHistoryItem])
def get_decision_history(request: Request, since: int | None = None, limit: int = 50):
    """List past decision results (evaluated_at, status, memo) for the Past advice view."""
    with app_db_connection(request.app) as conn:
        rows = list_decision_history(conn, since=since, limit=limit)
        return [
            DecisionHistoryItem(id=r[0], evaluated_at=r[1], status=r[2], memo=r[3], trigger_ids=r[4])
            for r in rows
        ]


@app.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(request: Request, days: int = 365):
    """Deterministic maturity and obligation summary for the Home view."""
    days = max(1, min(days, 3650))
    with app_db_connection(request.app) as conn:
        data = build_dashboard(conn, days=days)
        return DashboardResponse(**data)


@app.post("/positions/confirm-extraction", response_model=ConfirmExtractionResponse)
def confirm_extraction(request: Request, body: ConfirmExtractionRequest):
    """Accept or dismiss a structured position suggestion from document ingest."""
    with app_db_connection(request.app) as conn:
        if not doc_exist(conn, body.document_id):
            raise HTTPException(status_code=404, detail="Document not found")
        if not body.accept:
            clear_document_extracted_position(conn, body.document_id)
            conn.commit()
            return ConfirmExtractionResponse(accepted=False, message="Suggestion dismissed.")
        position = apply_position_extraction(
            conn, body.document_id, overrides=body.overrides
        )
        if position is None:
            raise HTTPException(status_code=404, detail="No pending extraction for this document")
        conn.commit()
        return ConfirmExtractionResponse(
            accepted=True,
            account_id=position.account_id,
            position=position,
            message="Position added.",
        )


@app.post("/obligations/confirm-extraction", response_model=ConfirmObligationExtractionResponse)
def confirm_obligation_extraction(request: Request, body: ConfirmObligationExtractionRequest):
    """Accept or dismiss a structured obligation suggestion from document ingest."""
    with app_db_connection(request.app) as conn:
        if not doc_exist(conn, body.document_id):
            raise HTTPException(status_code=404, detail="Document not found")
        if not body.accept:
            clear_document_extracted_obligation(conn, body.document_id)
            conn.commit()
            return ConfirmObligationExtractionResponse(accepted=False, message="Suggestion dismissed.")
        obligation = apply_obligation_extraction(
            conn, body.document_id, overrides=body.overrides
        )
        if obligation is None:
            raise HTTPException(
                status_code=404, detail="No pending obligation extraction for this document"
            )
        conn.commit()
        return ConfirmObligationExtractionResponse(
            accepted=True,
            obligation=obligation,
            message="Obligation added.",
        )


@app.post("/positions/{position_id}/resolve", response_model=PositionResponse)
def resolve_position_route(request: Request, position_id: str, body: ResolvePositionRequest):
    with app_db_connection(request.app) as conn:
        row = get_position(conn, position_id)
        if not row:
            raise HTTPException(status_code=404, detail="Position not found")
        now = int(time.time())
        if body.action == "renewed":
            if not body.new_maturity_date or not str(body.new_maturity_date).strip():
                raise HTTPException(status_code=400, detail="new_maturity_date is required when renewing")
            resolve_position(conn, position_id, now, body.new_maturity_date.strip()[:10])
        else:
            resolve_position(conn, position_id, now, None)
        conn.commit()
        row = get_position(conn, position_id)
        if not row:
            raise HTTPException(status_code=404, detail="Position not found")
        return PositionResponse(
            id=row[0],
            account_id=row[1],
            asset_type=row[2],
            description=row[3],
            principal=row[4],
            rate_apr=row[5],
            maturity_date=row[6],
            document_id=row[7],
            created_at=row[8],
            updated_at=row[9],
        )


@app.post("/obligations/{obligation_id}/resolve", response_model=ObligationResponse)
def resolve_obligation_route(request: Request, obligation_id: str, body: ResolveObligationRequest):
    with app_db_connection(request.app) as conn:
        row = get_obligation(conn, obligation_id)
        if not row:
            raise HTTPException(status_code=404, detail="Obligation not found")
        now = int(time.time())
        resolve_obligation(conn, obligation_id, now)
        conn.commit()
        return ObligationResponse(
            id=row[0],
            description=row[1],
            due_date=row[2],
            amount_estimate=row[3],
            priority=row[4],
            document_id=row[5],
            created_at=row[6],
        )


# --- Financial CRUD ---

@app.get("/accounts", response_model=list[AccountResponse])
def list_accounts_route(request: Request):
    with app_db_connection(request.app) as conn:
        rows = list_accounts(conn)
        return [AccountResponse(id=r[0], name=r[1], type=r[2], institution=r[3], document_id=r[4], created_at=r[5]) for r in rows]


@app.post("/accounts", response_model=AccountResponse)
def create_account(request: Request, body: AccountCreate):
    import uuid
    acc_id = str(uuid.uuid4())
    now = int(time.time())
    with app_db_connection(request.app) as conn:
        insert_account(conn, acc_id, body.name, now, body.type, body.institution, body.document_id)
        conn.commit()
    return AccountResponse(id=acc_id, name=body.name, type=body.type, institution=body.institution, document_id=body.document_id, created_at=now)


@app.get("/accounts/{account_id}", response_model=AccountResponse)
def get_account_route(request: Request, account_id: str):
    with app_db_connection(request.app) as conn:
        row = get_account(conn, account_id)
        if not row:
            raise HTTPException(status_code=404, detail="Account not found")
        return AccountResponse(id=row[0], name=row[1], type=row[2], institution=row[3], document_id=row[4], created_at=row[5])


@app.patch("/accounts/{account_id}", response_model=AccountResponse)
def patch_account(request: Request, account_id: str, body: AccountUpdate):
    with app_db_connection(request.app) as conn:
        row = get_account(conn, account_id)
        if not row:
            raise HTTPException(status_code=404, detail="Account not found")
        update_account(conn, account_id, body.name, body.type, body.institution, body.document_id)
        conn.commit()
        row = get_account(conn, account_id)
        return AccountResponse(id=row[0], name=row[1], type=row[2], institution=row[3], document_id=row[4], created_at=row[5])


@app.delete("/accounts/{account_id}", status_code=204)
def delete_account_route(request: Request, account_id: str):
    with app_db_connection(request.app) as conn:
        if not get_account(conn, account_id):
            raise HTTPException(status_code=404, detail="Account not found")
        delete_account(conn, account_id)
        conn.commit()
    return None


@app.get("/positions", response_model=list[PositionResponse])
def list_positions_route(request: Request, account_id: str | None = None):
    with app_db_connection(request.app) as conn:
        rows = list_positions(conn, account_id)
        return [_position_row_to_response(r) for r in rows]


@app.post("/positions", response_model=PositionResponse)
def create_position(request: Request, body: PositionCreate):
    import uuid
    pos_id = str(uuid.uuid4())
    now = int(time.time())
    with app_db_connection(request.app) as conn:
        if not get_account(conn, body.account_id):
            raise HTTPException(status_code=400, detail="Account not found")
        insert_position(
            conn,
            pos_id,
            body.account_id,
            body.asset_type,
            now,
            now,
            body.description,
            body.principal,
            body.rate_apr,
            body.maturity_date,
            body.document_id,
            body.start_date,
            body.next_action,
            body.liquidity_note,
        )
        conn.commit()
    return PositionResponse(
        id=pos_id,
        account_id=body.account_id,
        asset_type=body.asset_type,
        description=body.description,
        principal=body.principal,
        rate_apr=body.rate_apr,
        maturity_date=body.maturity_date,
        document_id=body.document_id,
        start_date=body.start_date,
        next_action=body.next_action,
        liquidity_note=body.liquidity_note,
        created_at=now,
        updated_at=now,
    )


@app.get("/positions/{position_id}", response_model=PositionResponse)
def get_position_route(request: Request, position_id: str):
    with app_db_connection(request.app) as conn:
        row = get_position(conn, position_id)
        if not row:
            raise HTTPException(status_code=404, detail="Position not found")
        return _position_row_to_response(row)


@app.patch("/positions/{position_id}", response_model=PositionResponse)
def patch_position(request: Request, position_id: str, body: PositionUpdate):
    now = int(time.time())
    with app_db_connection(request.app) as conn:
        row = get_position(conn, position_id)
        if not row:
            raise HTTPException(status_code=404, detail="Position not found")
        update_position(
            conn,
            position_id,
            now,
            body.description,
            body.principal,
            body.rate_apr,
            body.maturity_date,
            body.document_id,
            body.start_date,
            body.next_action,
            body.liquidity_note,
        )
        conn.commit()
        row = get_position(conn, position_id)
        return _position_row_to_response(row)


@app.delete("/positions/{position_id}", status_code=204)
def delete_position_route(request: Request, position_id: str):
    with app_db_connection(request.app) as conn:
        if not get_position(conn, position_id):
            raise HTTPException(status_code=404, detail="Position not found")
        delete_position(conn, position_id)
        conn.commit()
    return None


@app.get("/obligations", response_model=list[ObligationResponse])
def list_obligations_route(request: Request):
    with app_db_connection(request.app) as conn:
        rows = list_obligations(conn)
        return [
            ObligationResponse(id=r[0], description=r[1], due_date=r[2], amount_estimate=r[3], priority=r[4], document_id=r[5], created_at=r[6])
            for r in rows
        ]


@app.post("/obligations", response_model=ObligationResponse)
def create_obligation(request: Request, body: ObligationCreate):
    import uuid
    obl_id = str(uuid.uuid4())
    now = int(time.time())
    with app_db_connection(request.app) as conn:
        insert_obligation(conn, obl_id, body.description, body.due_date, now, body.amount_estimate, body.priority, body.document_id)
        conn.commit()
    return ObligationResponse(id=obl_id, description=body.description, due_date=body.due_date, amount_estimate=body.amount_estimate, priority=body.priority, document_id=body.document_id, created_at=now)


@app.get("/obligations/{obligation_id}", response_model=ObligationResponse)
def get_obligation_route(request: Request, obligation_id: str):
    with app_db_connection(request.app) as conn:
        row = get_obligation(conn, obligation_id)
        if not row:
            raise HTTPException(status_code=404, detail="Obligation not found")
        return ObligationResponse(id=row[0], description=row[1], due_date=row[2], amount_estimate=row[3], priority=row[4], document_id=row[5], created_at=row[6])


@app.patch("/obligations/{obligation_id}", response_model=ObligationResponse)
def patch_obligation(request: Request, obligation_id: str, body: ObligationUpdate):
    with app_db_connection(request.app) as conn:
        row = get_obligation(conn, obligation_id)
        if not row:
            raise HTTPException(status_code=404, detail="Obligation not found")
        update_obligation(conn, obligation_id, body.description, body.due_date, body.amount_estimate, body.priority, body.document_id)
        conn.commit()
        row = get_obligation(conn, obligation_id)
        return ObligationResponse(id=row[0], description=row[1], due_date=row[2], amount_estimate=row[3], priority=row[4], document_id=row[5], created_at=row[6])


@app.delete("/obligations/{obligation_id}", status_code=204)
def delete_obligation_route(request: Request, obligation_id: str):
    with app_db_connection(request.app) as conn:
        if not get_obligation(conn, obligation_id):
            raise HTTPException(status_code=404, detail="Obligation not found")
        delete_obligation(conn, obligation_id)
        conn.commit()
    return None


@app.get("/ira-overview", response_model=list[IraOverviewResponse])
def list_ira_overview_route(request: Request):
    with app_db_connection(request.app) as conn:
        return [_ira_row_to_response(r) for r in list_ira_overview(conn)]


@app.post("/ira-overview", response_model=IraOverviewResponse)
def create_ira_overview_route(request: Request, body: IraOverviewCreate):
    import uuid
    ira_id = str(uuid.uuid4())
    now = int(time.time())
    with app_db_connection(request.app) as conn:
        insert_ira_overview(
            conn,
            ira_id,
            body.account_name,
            now,
            now,
            body.institution,
            body.account_type,
            body.balance_estimate,
            body.rmd_note,
            body.next_relevant_date,
            body.document_id,
        )
        conn.commit()
    return IraOverviewResponse(
        id=ira_id,
        account_name=body.account_name,
        institution=body.institution,
        account_type=body.account_type,
        balance_estimate=body.balance_estimate,
        rmd_note=body.rmd_note,
        next_relevant_date=body.next_relevant_date,
        document_id=body.document_id,
        created_at=now,
        updated_at=now,
    )


@app.get("/ira-overview/{ira_id}", response_model=IraOverviewResponse)
def get_ira_overview_route(request: Request, ira_id: str):
    with app_db_connection(request.app) as conn:
        row = get_ira_overview(conn, ira_id)
        if not row:
            raise HTTPException(status_code=404, detail="IRA overview not found")
        return _ira_row_to_response(row)


@app.patch("/ira-overview/{ira_id}", response_model=IraOverviewResponse)
def patch_ira_overview_route(request: Request, ira_id: str, body: IraOverviewUpdate):
    now = int(time.time())
    with app_db_connection(request.app) as conn:
        row = get_ira_overview(conn, ira_id)
        if not row:
            raise HTTPException(status_code=404, detail="IRA overview not found")
        update_ira_overview(
            conn,
            ira_id,
            now,
            body.account_name,
            body.institution,
            body.account_type,
            body.balance_estimate,
            body.rmd_note,
            body.next_relevant_date,
            body.document_id,
        )
        conn.commit()
        row = get_ira_overview(conn, ira_id)
        return _ira_row_to_response(row)


@app.delete("/ira-overview/{ira_id}", status_code=204)
def delete_ira_overview_route(request: Request, ira_id: str):
    with app_db_connection(request.app) as conn:
        if not get_ira_overview(conn, ira_id):
            raise HTTPException(status_code=404, detail="IRA overview not found")
        delete_ira_overview(conn, ira_id)
        conn.commit()
    return None


@app.get("/health")
def health():
    ask_mode = "queued" if _is_portable_profile() else "stream"
    return {"healthy": True, "ask_mode": ask_mode, "profile": _portable_profile() or "default"}


@app.post("/warmup/ask", response_model=WarmupResponse)
async def warmup_ask():
    result = await request_warmup("ask")
    return WarmupResponse(**result)


@app.post("/warmup/ingest", response_model=WarmupResponse)
async def warmup_ingest():
    result = await request_warmup("ingest")
    return WarmupResponse(**result)


@app.get("/warmup/status", response_model=WarmupStatusResponse)
def warmup_status():
    return WarmupStatusResponse(**get_warmup_status())


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=error_envelope(exc.detail, http_error_code(exc.status_code), request=request),
    )


@app.exception_handler(httpx.ConnectError)
async def httpx_connect_error_handler(request: Request, exc: httpx.ConnectError):
    _remote_log_error(request, f"Upstream connect failed: {str(exc)[:500]}", "httpx.ConnectError")
    logger.warning("Upstream connection failed: %s", exc)
    return JSONResponse(
        status_code=503,
        content=error_envelope(
            (
                "Cannot reach the AI backend or another upstream service. It may still be starting "
                "or offline. Ask the administrator to check Ledgerly logs or Docker/Ollama."
            ),
            "upstream_connect",
            request=request,
        ),
    )


@app.exception_handler(httpx.TimeoutException)
async def httpx_timeout_exception_handler(request: Request, exc: httpx.TimeoutException):
    """Covers ConnectTimeout, ReadTimeout, PoolTimeout, WriteTimeout, etc."""
    _remote_log_error(request, f"{type(exc).__name__}: {str(exc)[:500]}", type(exc).__name__)
    logger.warning("Upstream HTTP timeout (%s): %s", type(exc).__name__, exc)
    if isinstance(exc, httpx.ConnectTimeout):
        detail = (
            "Timed out connecting to the AI backend or another upstream service. "
            "If this persists, the administrator should verify Ollama and network/Docker routing."
        )
        code = "upstream_connect"
    elif isinstance(exc, httpx.ReadTimeout):
        detail = (
            "The AI backend took too long to reply. Wait and try again, or ask "
            "the administrator to check model load or increase timeouts."
        )
        code = "llm_timeout"
    else:
        detail = (
            "A network request to the AI backend or another upstream service timed out. "
            "Wait and retry, or ask the administrator to check service load."
        )
        code = "llm_timeout"
    return JSONResponse(
        status_code=504,
        content=error_envelope(detail, code, request=request),
    )


@app.exception_handler(LLMTimeoutError)
async def llm_timeout_handler(request: Request, exc: LLMTimeoutError):
    _remote_log_error(request, "LLM request timed out", "LLMTimeoutError")
    return JSONResponse(
        status_code=504,
        content=error_envelope(
            "The AI backend timed out. Wait and retry, or ask the administrator for help.",
            "llm_timeout",
            request=request,
        ),
    )


@app.exception_handler(LLMUpstreamTimeoutError)
async def llm_upstream_timeout_handler(request: Request, exc: LLMUpstreamTimeoutError):
    _remote_log_error(request, "LLM upstream timed out", "LLMUpstreamTimeoutError")
    return JSONResponse(
        status_code=504,
        content=error_envelope(
            (
                "The embedding or AI backend timed out. Wait and retry with a smaller payload, "
                "or ask the administrator to check timeouts and service load."
            ),
            "llm_timeout",
            request=request,
        ),
    )


@app.exception_handler(LLMServiceError)
async def llm_service_error_handler(request: Request, exc: LLMServiceError):
    _remote_log_error(request, "LLM service unavailable", "LLMServiceError")
    detail = str(exc).strip() or "LLM service unavailable"
    return JSONResponse(
        status_code=503,
        content=error_envelope(detail, "llm_service", request=request),
    )


@app.exception_handler(LLMRateLimitedError)
async def llm_rate_limit_handler(request: Request, exc: LLMRateLimitedError):
    _remote_log_error(request, "LLM rate limit", "LLMRateLimitedError")
    return JSONResponse(
        status_code=429,
        content=error_envelope(
            "Too many assistant requests too quickly. Wait briefly and try again.",
            "rate_limit",
            request=request,
        ),
    )


@app.exception_handler(Exception)
async def catch_all_exception_handler(request: Request, exc: Exception):
    _remote_log_error(
        request,
        f"{type(exc).__name__}: {str(exc)[:500]}",
        type(exc).__name__,
    )
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content=error_envelope(
            (
                "An unexpected error occurred. Try again later. "
                "If it persists, send the administrator the Reference ID shown here."
            ),
            "internal_error",
            request=request,
        ),
    )


def _google_flow():
    """Build OAuth flow for Drive read-only (state will be set per-request)."""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise ValueError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set")
    from google_auth_oauthlib.flow import Flow

    client_config = {
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uris": [GOOGLE_REDIRECT_URI],
        }
    }
    return Flow.from_client_config(
        client_config,
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
        redirect_uri=GOOGLE_REDIRECT_URI,
    )


@app.get("/auth/google")
async def auth_google(request: Request):
    """
    Start one-time OAuth: redirect to Google consent (Drive read-only).
    After approval, user is sent to /auth/google/callback.
    """
    try:
        flow = _google_flow()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    auth_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="false",
    )
    response = RedirectResponse(url=auth_url, status_code=302)
    response.set_cookie(key="oauth_state", value=state, max_age=600, httponly=True)
    return response


@app.get("/auth/google/callback", response_class=HTMLResponse)
async def auth_google_callback(request: Request):
    """
    OAuth callback: exchange code for tokens, show refresh token to set in .env.
    """
    state_cookie = request.cookies.get("oauth_state")
    state_query = request.query_params.get("state")
    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Missing code in callback")
    if not state_cookie or state_cookie != state_query:
        raise HTTPException(status_code=400, detail="Invalid or missing state")
    try:
        flow = _google_flow()
        flow._state = state_query
        flow.fetch_token(authorization_response=str(request.url))
    except Exception as e:
        logger.exception("OAuth fetch_token failed: %s", e)
        raise HTTPException(status_code=503, detail="Token exchange failed") from e
    refresh_token = flow.credentials.refresh_token
    if not refresh_token:
        raise HTTPException(
            status_code=503,
            detail="No refresh token; try revoking app access and re-authorizing with prompt=consent",
        )
    response = HTMLResponse(
        content=f"""
        <html><body style="font-family: sans-serif; padding: 2rem;">
        <h1>Google Drive auth complete</h1>
        <p>Add this to your <code>.env</code> (or set the env var):</p>
        <pre style="background: #eee; padding: 1rem; overflow-x: auto;">GOOGLE_REFRESH_TOKEN={refresh_token!r}</pre>
        <p>You already have <code>GOOGLE_CLIENT_ID</code> and <code>GOOGLE_CLIENT_SECRET</code> set (required for this flow).</p>
        <p>Then restart the app and use <b>POST /ingest/google-drive</b> to sync.</p>
        </body></html>
        """
    )
    response.delete_cookie("oauth_state")
    return response


# Serve frontend (tabs + documents drawer); 
# mount last so API routes take precedence
static_dir = Path(__file__).resolve().parent.parent / "static"
if static_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

