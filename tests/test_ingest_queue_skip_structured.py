"""Queued ingest skips structured LLM extraction to keep CPU cooler."""

from __future__ import annotations

import sqlite3

import pytest

from app import main as main_module
from app.db import create_db, list_documents_with_extracted_position
from app.ingest_jobs import IngestJob, IngestJobKind
from app.main import ingest_text
from app.models import ChunkingOptions


def test_ingest_job_defaults_skip_structured() -> None:
    job = IngestJob(id="j1", kind=IngestJobKind.PDF, doc_id="d1")
    assert job.skip_structured is True


class _MockEmbedder:
    model = "nomic-embed-text"
    dim = 768

    async def embed_many(self, texts, **kwargs):
        return [[0.0] * self.dim for _ in texts]


@pytest.mark.asyncio
async def test_ingest_text_skip_structured_does_not_call_extractors(monkeypatch, tmp_path):
    db_file = tmp_path / "skip_structured.db"
    conn = sqlite3.connect(str(db_file))
    create_db(conn)

    monkeypatch.setattr(main_module, "INGEST_AUTO_TRACK_ENABLED", True)
    monkeypatch.setattr(main_module, "INGEST_STRUCTURED_ENABLED", True)
    monkeypatch.setattr(main_module, "HttpEmbedder", lambda *a, **k: _MockEmbedder())

    async def fail_position(text, title):
        raise AssertionError("structured position must not run when skip_structured=True")

    async def fail_obligation(text, title):
        raise AssertionError("structured obligation must not run when skip_structured=True")

    monkeypatch.setattr(main_module, "extract_structured_position", fail_position)
    monkeypatch.setattr(main_module, "extract_structured_obligation", fail_obligation)

    resp = await ingest_text(
        conn,
        "doc-queue-1",
        "CD letter",
        "upload",
        "Certificate of deposit matures March 15 2026.",
        ChunkingOptions(chunk_size=80, chunk_overlap=10),
        skip_structured=True,
    )
    assert resp.extracted_position is None
    assert resp.extracted_obligation is None
    assert resp.auto_tracked_position is None
    assert not list_documents_with_extracted_position(conn)
    assert resp.num_chunks >= 1
