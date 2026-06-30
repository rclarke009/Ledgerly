"""Background worker: process queued ask jobs one at a time."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.ask_graph import build_prompt_and_chunks
from app.ask_history import update_job_result
from app.ask_jobs import AskJob, AskJobStatus
from app.ask_queue import AskJobStore
from app.answer_format import merge_structured_to_response, normalize_markdown_layout, split_structured
from app.config import ASK_QUEUE_INTER_JOB_SLEEP_SEC
from app.db_connection import app_db_connection
from app.models import AskRequest
from app import llm_client

logger = logging.getLogger(__name__)


async def _run_one_ask(app: Any, store: AskJobStore, job: AskJob) -> None:
    ask_request = AskRequest(
        question=job.question,
        top_k=job.top_k,
        doc_id=job.doc_id,
        tag=job.tag,
        use_rag=job.use_rag,
        conversation_id=job.conversation_id,
    )

    async def progress(stage: str) -> None:
        job.stage = stage
        if stage == "routing":
            job.progress_pct = 10.0
        elif stage == "searching":
            job.progress_pct = 40.0
        elif stage == "generating":
            job.progress_pct = 70.0
        await store.update(job)

    with app_db_connection(app) as conn:
        messages, top_chunks, route, has_context, direct_answer, related_documents = (
            await build_prompt_and_chunks(conn, ask_request, progress_cb=progress)
        )
        job.route = route
        job.top_chunks = [
            c.model_dump() if hasattr(c, "model_dump") else dict(c) for c in top_chunks
        ]
        job.related_documents = [d.model_dump() for d in related_documents]
        job.turn_id = job.id

        if not has_context:
            job.status = AskJobStatus.SUCCESS
            job.stage = "done"
            job.progress_pct = 100.0
            job.answer = "I don't have relevant context or data to answer that question."
            await store.update(job)
            update_job_result(
                conn,
                job.id,
                status="complete",
                answer=job.answer,
                route=route,
                related_documents=related_documents,
                top_chunks=job.top_chunks,
            )
            return

        if direct_answer:
            job.status = AskJobStatus.SUCCESS
            job.stage = "done"
            job.progress_pct = 100.0
            job.answer = normalize_markdown_layout(direct_answer)
            await store.update(job)
            update_job_result(
                conn,
                job.id,
                status="complete",
                answer=job.answer,
                route=route,
                related_documents=related_documents,
                top_chunks=job.top_chunks,
            )
            return

        await progress("generating")
        rate_limiter = app.state.rate_limiter
        await rate_limiter.acquire()
        raw = await llm_client.answer_with_messages(messages)
        body, tail = split_structured(raw)
        answer, tables, charts = merge_structured_to_response(body, tail)
        job.status = AskJobStatus.SUCCESS
        job.stage = "done"
        job.progress_pct = 100.0
        job.answer = normalize_markdown_layout(answer)
        job.tables = [t.model_dump() for t in tables]
        job.charts = [c.model_dump() for c in charts]
        await store.update(job)
        update_job_result(
            conn,
            job.id,
            status="complete",
            answer=job.answer,
            tables=job.tables,
            charts=job.charts,
            route=route,
            related_documents=related_documents,
            top_chunks=job.top_chunks,
        )


async def ask_worker_loop(app: Any) -> None:
    store: AskJobStore = app.state.ask_job_store
    while True:
        try:
            job = await store.pop_next_pending()
            if job is None:
                await asyncio.sleep(0.5)
                continue
            try:
                await _run_one_ask(app, store, job)
            except Exception as e:
                logger.exception("Ask job %s failed", job.id)
                job.status = AskJobStatus.FAILED
                job.stage = "failed"
                job.error = str(e)
                await store.update(job)
                with app_db_connection(app) as conn:
                    update_job_result(conn, job.id, status="failed", error=str(e))
            if ASK_QUEUE_INTER_JOB_SLEEP_SEC > 0:
                await asyncio.sleep(ASK_QUEUE_INTER_JOB_SLEEP_SEC)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("ask_worker_loop error: %s", e)
            await asyncio.sleep(1.0)
