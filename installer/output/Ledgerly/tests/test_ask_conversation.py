"""Tests for conversational Ask: context, sources, and history."""

from __future__ import annotations

import json
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from app.ask_conversation import expand_retrieval_query, load_conversation_turns, resolve_doc_scope
from app.ask_history import fetch_ask_history, insert_complete_answer
from app.ask_sources import detect_related_documents
from app.db import create_db, insert_document, set_document_tags
from app.main import app
from app.models import AskRequest, RetrievedChunk


@pytest.fixture
def conn(tmp_path):
    c = sqlite3.connect(str(tmp_path / "ask_conv.sqlite"))
    create_db(c)
    yield c
    c.close()


@pytest.fixture
def client_with_db(tmp_path):
    db_file = tmp_path / "ask_conv_api.sqlite"
    conn = sqlite3.connect(str(db_file))
    create_db(conn)
    conn.close()
    app.state.use_postgres = False
    app.state.db_path = str(db_file)
    yield TestClient(app)
    app.state.db_path = None


def test_expand_retrieval_query_with_prior_turn():
    prior = [{"role": "user", "content": "When does my CD mature?"}]
    assert expand_retrieval_query("What about the rate?", prior) == (
        "When does my CD mature? | What about the rate?"
    )


def test_expand_retrieval_query_without_prior():
    assert expand_retrieval_query("What about the rate?", []) == "What about the rate?"


def test_load_conversation_turns_respects_max_turns(conn):
    conv_id = None
    for i in range(8):
        if i == 0:
            req = AskRequest(question=f"Question {i}")
        else:
            req = AskRequest(question=f"Question {i}", conversation_id=conv_id)
        result = insert_complete_answer(conn, req, f"Answer {i}", route="rag")
        if i == 0:
            conv_id = result.conversation_id
    conn.commit()

    turns = load_conversation_turns(conn, conv_id, max_turns=3)
    assert len(turns) <= 6
    assert turns[-1]["content"] == "Answer 7"


def test_resolve_doc_scope_inherits_from_conversation(conn):
    first = AskRequest(question="About my CD letter", doc_id="cd-doc-1")
    result = insert_complete_answer(conn, first, "First answer", route="rag")
    conn.commit()

    follow = AskRequest(question="What is the rate?", conversation_id=result.conversation_id)
    scoped = resolve_doc_scope(conn, follow)
    assert scoped.doc_id == "cd-doc-1"


def test_detect_related_documents_merges_sources(conn):
    now = int(time.time())
    insert_document(conn, "cd-doc", now, title="CD Maturity Letter", source="cd.pdf")
    insert_document(conn, "tax-doc", now, title="1099 Form", source="1099.pdf")
    set_document_tags(conn, "tax-doc", ["2024"])
    conn.commit()

    req = AskRequest(question="About my CD", doc_id="cd-doc")
    chunks = [
        RetrievedChunk(chunk_id="tax-doc:0", doc_id="tax-doc", score=0.9, content_snippet="1099"),
        RetrievedChunk(chunk_id="cd-doc:0", doc_id="cd-doc", score=0.85, content_snippet="CD"),
    ]
    related = detect_related_documents(conn, req, chunks, "About my CD")
    reasons = {d.doc_id: d.reason for d in related}
    assert reasons["cd-doc"] == "pinned"
    assert reasons["tax-doc"] == "retrieved"


def test_insert_complete_answer_assigns_conversation_and_parent(conn):
    first_req = AskRequest(question="First question")
    first = insert_complete_answer(conn, first_req, "First answer", route="rag")
    conn.commit()

    second_req = AskRequest(question="Follow-up", conversation_id=first.conversation_id)
    second = insert_complete_answer(conn, second_req, "Second answer", route="rag")
    conn.commit()

    items = fetch_ask_history(conn)
    by_id = {item.id: item for item in items}
    assert first.conversation_id == second.conversation_id
    assert by_id[second.turn_id].parent_id == first.turn_id


def test_get_ask_conversation_endpoint(client_with_db, tmp_path):
    db_file = tmp_path / "ask_conv_api.sqlite"
    conn = sqlite3.connect(str(db_file))
    req = AskRequest(question="Hello")
    turn = insert_complete_answer(conn, req, "Hi there", route="rag")
    follow = AskRequest(question="Follow-up", conversation_id=turn.conversation_id)
    insert_complete_answer(conn, follow, "More detail", route="rag")
    conn.commit()
    conn.close()

    res = client_with_db.get(f"/ask/conversations/{turn.conversation_id}")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 2
    assert data[0]["question"] == "Hello"
    assert data[1]["question"] == "Follow-up"


def test_get_ask_conversation_not_found(client_with_db):
    res = client_with_db.get("/ask/conversations/does-not-exist")
    assert res.status_code == 404


def test_ask_meta_payload_includes_conversation_id():
    """Stream/queue final lines must carry conversation_id for follow-up UI."""
    from app.main import _ask_meta_payload

    payload = _ask_meta_payload(
        conversation_id="abc123",
        turn_id="turn456",
        related_documents=[],
    )
    assert payload["conversation_id"] == "abc123"
    assert payload["turn_id"] == "turn456"
