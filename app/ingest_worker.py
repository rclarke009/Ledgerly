"""Background worker: process queued ingest jobs one at a time."""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import INGEST_QUEUE_INTER_JOB_SLEEP_SEC
from app.db_connection import app_db_connection
from app.ingest_jobs import IngestJob, IngestJobKind, IngestJobStatus
from app.ingest_queue import IngestJobStore
from app.models import ChunkingOptions
from app import llm_client

logger = logging.getLogger(__name__)

# Magic bytes (duplicated from main to avoid circular import at module level)
PDF_MAGIC = b"%PDF"
JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
INGEST_PDF_MAX_BYTES = 20 * 1024 * 1024
INGEST_IMAGE_MAX_BYTES = 10 * 1024 * 1024


async def _job_progress(
    store: IngestJobStore,
    job: IngestJob,
    stage: str,
    progress_pct: float,
    *,
    batches_done: int | None = None,
    total_embed_batches: int | None = None,
) -> None:
    job.stage = stage
    job.progress_pct = min(100.0, max(0.0, progress_pct))
    now_m = time.perf_counter()
    if stage == "embedding" and progress_pct <= 20.0:
        job._embed_started_at = now_m
    if (
        batches_done is not None
        and total_embed_batches
        and batches_done > 0
        and job._embed_started_at is not None
    ):
        elapsed = now_m - job._embed_started_at
        avg_per_batch = elapsed / batches_done
        remaining_batches = total_embed_batches - batches_done
        fudge = 8.0
        job.eta_seconds = max(0, int(remaining_batches * avg_per_batch + fudge))
        job.estimated_completion_at = datetime.now(timezone.utc) + timedelta(
            seconds=job.eta_seconds
        )
    elif stage in ("chunking", "extracting", "facts", "saving") or (
        stage == "embedding" and progress_pct <= 20.0
    ):
        job.eta_seconds = None
        job.estimated_completion_at = None
    await store.update(job)


async def _run_one_job(app: Any, store: IngestJobStore, job: IngestJob) -> None:
    from app.main import (
        DuplicateContentError,
        ingest_text,
        _is_supported_image,
        _strip_nul_bytes,
    )
    from app.pdf_ingest import parse_pdf_text_mode, resolve_pdf_for_ingest

    chunking = ChunkingOptions(chunk_size=job.chunk_size, chunk_overlap=job.chunk_overlap)

    async def progress_cb(stage: str, pct: float, **kwargs: Any) -> None:
        await _job_progress(
            store,
            job,
            stage,
            pct,
            batches_done=kwargs.get("batches_done"),
            total_embed_batches=kwargs.get("total_embed_batches"),
        )

    text: str
    vault_original: tuple[str, bytes] | None = None
    canonical_original_vault_rel: str | None = None
    persist_snap = True
    if job.kind == IngestJobKind.TEXT:
        if not job.text_content:
            raise ValueError("TEXT job missing text_content")
        text = job.text_content
    else:
        if job.keep_incoming_original_rel:
            from app import originals_vault as ov_mod

            p_src = ov_mod.absolute_from_vault_relative(job.keep_incoming_original_rel)
            if not p_src or not p_src.is_file():
                raise FileNotFoundError("Vault original missing")
            raw = p_src.read_bytes()
            fname = job.filename or (
                "upload.pdf" if job.kind == IngestJobKind.PDF else "upload.jpg"
            )
            vault_original = None
            canonical_original_vault_rel = job.keep_incoming_original_rel
            persist_snap = False
        else:
            if not job.temp_path or not os.path.isfile(job.temp_path):
                raise FileNotFoundError("Temp upload missing")
            raw = open(job.temp_path, "rb").read()
            fname = job.filename or (
                "upload.pdf" if job.kind == IngestJobKind.PDF else "upload.jpg"
            )
            vault_original = (fname, raw)
            persist_snap = False
        if job.kind == IngestJobKind.PDF:
            if len(raw) > INGEST_PDF_MAX_BYTES:
                raise ValueError("PDF too large")
            if not raw.startswith(PDF_MAGIC):
                raise ValueError("Not a PDF")
            await progress_cb("extracting", 5.0)
            text = await resolve_pdf_for_ingest(raw, parse_pdf_text_mode(job.pdf_text_mode))
            text = _strip_nul_bytes((text or "").strip())
            if not text:
                raise ValueError("No text extracted from PDF")
        else:
            if len(raw) > INGEST_IMAGE_MAX_BYTES:
                raise ValueError("Image too large")
            if not _is_supported_image(raw):
                raise ValueError("Unsupported image type")
            await progress_cb("extracting", 5.0)
            image_base64 = base64.b64encode(raw).decode("ascii")
            hint = job.source or job.title or (
                "upload.pdf" if job.kind == IngestJobKind.PDF else "upload.jpg"
            )
            text = await llm_client.image_to_text_for_ingest(image_base64, filename_hint=hint)
            text = _strip_nul_bytes((text or "").strip())
            if len(text) < 10:
                raise ValueError("No text extracted from image")

    with app_db_connection(app) as conn:
        try:
            resp = await ingest_text(
                conn,
                job.doc_id,
                job.title,
                job.source,
                text,
                chunking,
                confirm_duplicate_content=job.confirm_duplicate_content,
                tags=job.tags,
                account_id=job.account_id,
                progress=progress_cb,
                vault_original=vault_original,
                persist_normalized_text_snapshot=persist_snap,
                canonical_original_vault_rel=canonical_original_vault_rel,
            )
        except DuplicateContentError as e:
            job.status = IngestJobStatus.FAILED
            job.error = f"Duplicate content (existing doc_id={e.existing_doc_id!r})"
            job.progress_pct = 0.0
            await store.update(job)
            return
        except ValueError as e:
            if "already exists" in str(e):
                job.status = IngestJobStatus.FAILED
                job.error = str(e)
                await store.update(job)
                return
            raise
        job.status = IngestJobStatus.SUCCESS
        job.progress_pct = 100.0
        job.stage = "done"
        job.eta_seconds = None
        job.estimated_completion_at = None
        job.result = {
            "doc_id": resp.doc_id,
            "num_chunks": resp.num_chunks,
            "embedding_model": resp.embedding_model,
            "dim": resp.dim,
            "facts_learned": resp.facts_learned,
            "extracted_position": (
                resp.extracted_position.model_dump() if resp.extracted_position is not None else None
            ),
            "extracted_obligation": (
                resp.extracted_obligation.model_dump() if resp.extracted_obligation is not None else None
            ),
            "auto_tracked_position": (
                resp.auto_tracked_position.model_dump() if resp.auto_tracked_position is not None else None
            ),
            "auto_tracked_obligation": (
                resp.auto_tracked_obligation.model_dump() if resp.auto_tracked_obligation is not None else None
            ),
            "source": resp.source,
            "original_vault_path": resp.original_vault_path,
            "has_openable_original": resp.has_openable_original,
        }
        await store.update(job)


async def ingest_worker_loop(app: Any) -> None:
    """Single-threaded queue: one job at a time, optional pause between jobs."""
    store: IngestJobStore = app.state.ingest_job_store
    while True:
        try:
            job = await store.pop_next_pending()
            if job is None:
                await asyncio.sleep(0.5)
                continue
            try:
                await _run_one_job(app, store, job)
            except Exception as e:
                logger.exception("Ingest job %s failed", job.id)
                job.status = IngestJobStatus.FAILED
                job.error = str(e)
                job.stage = "failed"
                await store.update(job)
            finally:
                if job.temp_path:
                    try:
                        if os.path.isfile(job.temp_path):
                            os.unlink(job.temp_path)
                    except OSError as ex:
                        logger.warning("Could not remove temp %s: %s", job.temp_path, ex)
                    job.temp_path = None
                    await store.update(job)

            if INGEST_QUEUE_INTER_JOB_SLEEP_SEC > 0:
                await asyncio.sleep(INGEST_QUEUE_INTER_JOB_SLEEP_SEC)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("ingest_worker_loop error: %s", e)
            await asyncio.sleep(1.0)
