"""Tests for auto-track on ingest and extraction apply helpers."""

import json
import sqlite3
import time

import pytest

from app import main as main_module
from app.db import (
    create_db,
    doc_exist,
    get_obligations_by_document_id,
    get_positions_by_document_id,
    insert_document,
    list_documents_with_extracted_position,
    set_document_extracted_position,
)
from app.dashboard import build_dashboard
from app.extraction_apply import apply_obligation_extraction, apply_position_extraction
from app.main import ingest_text
from app.models import ChunkingOptions, ExtractedObligation, ExtractedPosition


class _MockEmbedder:
    model = "nomic-embed-text"
    dim = 768

    async def embed_many(self, texts, **kwargs):
        return [[0.0] * self.dim for _ in texts]


def test_apply_position_extraction(db_conn):
    now = int(time.time())
    insert_document(db_conn, "doc-apply-1", now, title="CD")
    set_document_extracted_position(
        db_conn,
        "doc-apply-1",
        json.dumps(
            {
                "institution": "Test Bank",
                "asset_type": "CD",
                "principal": 10000,
                "maturity_date": "2028-12-01",
                "confidence": "high",
            }
        ),
    )
    db_conn.commit()

    pos = apply_position_extraction(db_conn, "doc-apply-1")
    assert pos is not None
    assert pos.maturity_date == "2028-12-01"
    assert len(get_positions_by_document_id(db_conn, "doc-apply-1")) == 1
    assert not list_documents_with_extracted_position(db_conn)


def test_apply_obligation_extraction(db_conn):
    from app.db import set_document_extracted_obligation, list_documents_with_extracted_obligation

    now = int(time.time())
    insert_document(db_conn, "doc-obl-1", now, title="Bill")
    set_document_extracted_obligation(
        db_conn,
        "doc-obl-1",
        json.dumps(
            {
                "description": "Property tax",
                "due_date": "2026-04-01",
                "amount_estimate": 2500,
                "confidence": "high",
            }
        ),
    )
    db_conn.commit()

    obl = apply_obligation_extraction(db_conn, "doc-obl-1")
    assert obl is not None
    assert obl.due_date == "2026-04-01"
    assert len(get_obligations_by_document_id(db_conn, "doc-obl-1")) == 1
    assert not list_documents_with_extracted_obligation(db_conn)


@pytest.mark.asyncio
async def test_ingest_auto_tracks_position(monkeypatch, db_path):
    conn = sqlite3.connect(str(db_path))
    create_db(conn)

    monkeypatch.setattr(main_module, "INGEST_AUTO_TRACK_ENABLED", True)
    monkeypatch.setattr(main_module, "INGEST_STRUCTURED_ENABLED", True)
    monkeypatch.setattr(main_module, "HttpEmbedder", lambda *a, **k: _MockEmbedder())

    async def fake_position(text, title):
        return {
            "institution": "First National",
            "asset_type": "CD",
            "principal": 50000,
            "maturity_date": "2026-03-15",
            "confidence": "high",
        }

    async def no_obligation(text, title):
        return None

    monkeypatch.setattr(main_module, "extract_structured_position", fake_position)
    monkeypatch.setattr(main_module, "extract_structured_obligation", no_obligation)

    resp = await ingest_text(
        conn,
        "doc-auto-1",
        "CD letter",
        "upload",
        "Certificate of deposit matures March 15 2026.",
        ChunkingOptions(chunk_size=80, chunk_overlap=10),
    )
    assert resp.auto_tracked_position is not None
    assert resp.auto_tracked_position.maturity_date == "2026-03-15"
    assert len(get_positions_by_document_id(conn, "doc-auto-1")) == 1


@pytest.mark.asyncio
async def test_ingest_auto_track_disabled_leaves_pending(monkeypatch, db_path):
    conn = sqlite3.connect(str(db_path))
    create_db(conn)

    monkeypatch.setattr(main_module, "INGEST_AUTO_TRACK_ENABLED", False)
    monkeypatch.setattr(main_module, "INGEST_STRUCTURED_ENABLED", True)
    monkeypatch.setattr(main_module, "HttpEmbedder", lambda *a, **k: _MockEmbedder())

    async def fake_position(text, title):
        return {
            "asset_type": "CD",
            "maturity_date": "2026-03-15",
            "confidence": "high",
        }

    monkeypatch.setattr(main_module, "extract_structured_position", fake_position)
    monkeypatch.setattr(main_module, "extract_structured_obligation", lambda t, ti: None)

    resp = await ingest_text(
        conn,
        "doc-pending-1",
        "CD",
        None,
        "CD text here.",
        ChunkingOptions(chunk_size=80, chunk_overlap=10),
    )
    assert resp.auto_tracked_position is None
    assert resp.extracted_position is not None
    assert len(get_positions_by_document_id(conn, "doc-pending-1")) == 0
    assert list_documents_with_extracted_position(conn)
