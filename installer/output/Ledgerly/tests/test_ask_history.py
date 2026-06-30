"""Tests for Ask Ledgerly history persistence and GET /ask/history."""

import json
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from app.ask_history import fetch_ask_history, insert_complete_answer, insert_pending_for_job, update_job_result
from app.db import (
    create_db,
    insert_ask_history_complete,
    insert_ask_history_pending,
    list_ask_history,
    update_ask_history_result,
)
from app.main import app
from app.models import AskRequest


@pytest.fixture
def conn(tmp_path):
    c = sqlite3.connect(str(tmp_path / "ask_history.sqlite"))
    create_db(c)
    yield c
    c.close()


@pytest.fixture
def client_with_db(tmp_path):
    db_file = tmp_path / "ask_history_api.sqlite"
    conn = sqlite3.connect(str(db_file))
    create_db(conn)
    conn.close()
    app.state.use_postgres = False
    app.state.db_path = str(db_file)
    yield TestClient(app)
    app.state.db_path = None


def test_insert_pending_update_complete_list(conn):
    now = int(time.time())
    insert_ask_history_pending(
        conn,
        id="job-1",
        job_id="job-1",
        asked_at=now,
        question="How much in CDs?",
        doc_filter=None,
    )
    conn.commit()

    rows = list_ask_history(conn, limit=10)
    assert len(rows) == 1
    assert rows[0][3] == "pending"
    assert rows[0][4] == "How much in CDs?"

    tables = [{"title": "CDs", "columns": ["Bank", "Amount"], "rows": [["Chase", "1000"]]}]
    charts = [{"type": "bar", "title": "Holdings", "labels": ["CD"], "values": [1000]}]
    update_ask_history_result(
        conn,
        "job-1",
        status="complete",
        answer="You have $1,000 in CDs.",
        tables_json=json.dumps(tables),
        charts_json=json.dumps(charts),
        route="fast_path",
    )
    conn.commit()

    items = fetch_ask_history(conn, limit=10)
    assert len(items) == 1
    item = items[0]
    assert item.status == "complete"
    assert item.answer == "You have $1,000 in CDs."
    assert item.route == "fast_path"
    assert len(item.tables) == 1
    assert item.tables[0].title == "CDs"
    assert len(item.charts) == 1


def test_failed_job_update_sets_status_and_error(conn):
    now = int(time.time())
    insert_ask_history_pending(
        conn,
        id="job-fail",
        job_id="job-fail",
        asked_at=now,
        question="Will this fail?",
    )
    conn.commit()
    update_ask_history_result(
        conn,
        "job-fail",
        status="failed",
        error="LLM unavailable",
    )
    conn.commit()

    items = fetch_ask_history(conn)
    assert items[0].status == "failed"
    assert items[0].error == "LLM unavailable"
    assert items[0].answer is None


def test_insert_complete_answer_helper(conn):
    req = AskRequest(question="Summarize accounts", top_k=5)
    insert_complete_answer(
        conn,
        req,
        "You have two accounts.",
        tables=[],
        charts=[],
        route="rag",
        asked_at=time.time(),
    )
    conn.commit()

    items = fetch_ask_history(conn)
    assert len(items) == 1
    assert items[0].status == "complete"
    assert items[0].question == "Summarize accounts"
    assert items[0].job_id is None


def test_get_ask_history_endpoint(client_with_db, tmp_path):
    conn = sqlite3.connect(str(tmp_path / "ask_history_api.sqlite"))
    now = int(time.time())
    insert_ask_history_complete(
        conn,
        id="hist-1",
        asked_at=now,
        question="What bills are due?",
        answer="Your electric bill is due soon.",
    )
    conn.commit()
    conn.close()

    res = client_with_db.get("/ask/history")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["question"] == "What bills are due?"
    assert data[0]["status"] == "complete"
    assert data[0]["answer"] == "Your electric bill is due soon."


def test_pending_for_job_helper(conn):
    req = AskRequest(question="Queued question", top_k=5, doc_id="doc-abc")
    insert_pending_for_job(conn, "job-q", req, asked_at=time.time())
    conn.commit()

    items = fetch_ask_history(conn)
    assert items[0].status == "pending"
    assert items[0].job_id == "job-q"
    assert items[0].doc_filter == "doc-abc"
