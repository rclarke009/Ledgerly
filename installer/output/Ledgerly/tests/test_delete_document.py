"""Tests for document delete with cascade."""

import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from app.dashboard import build_dashboard
from app.db import (
    create_db,
    delete_document_cascade,
    doc_exist,
    get_obligations_by_document_id,
    get_positions_by_document_id,
    insert_account,
    insert_document,
    insert_obligation,
    insert_position,
)
from app.main import app


def _conn(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "delete_doc.sqlite"))
    create_db(conn)
    return conn


def test_delete_document_cascade_removes_linked_position(tmp_path):
    conn = _conn(tmp_path)
    now = int(time.time())
    insert_document(conn, "doc-cd-1", now, title="CD letter")
    insert_account(conn, "acc1", "Test Bank", now, institution="Test Bank", document_id="doc-cd-1")
    insert_position(
        conn,
        "pos1",
        "acc1",
        "CD",
        now,
        now,
        "12-month CD",
        10000.0,
        4.5,
        "2026-09-15",
        "doc-cd-1",
    )
    conn.commit()

    result = delete_document_cascade(conn, "doc-cd-1")
    conn.commit()

    assert result["positions_deleted"] == 1
    assert result["obligations_deleted"] == 0
    assert not doc_exist(conn, "doc-cd-1")
    assert not get_positions_by_document_id(conn, "doc-cd-1")
    data = build_dashboard(conn)
    assert data["next_maturity"] is None
    conn.close()


def test_delete_document_leaves_unlinked_position(tmp_path):
    conn = _conn(tmp_path)
    now = int(time.time())
    insert_document(conn, "doc-other", now, title="Generic PDF")
    insert_account(conn, "acc1", "Chase", now)
    insert_position(
        conn,
        "pos-manual",
        "acc1",
        "CD",
        now,
        now,
        "Manual CD",
        5000.0,
        3.0,
        "2027-01-01",
        None,
    )
    conn.commit()

    delete_document_cascade(conn, "doc-other")
    conn.commit()

    assert doc_exist(conn, "doc-other") is False
    positions = get_positions_by_document_id(conn, "doc-other")
    assert positions == []
    cursor = conn.execute("SELECT id FROM positions WHERE id = ?", ("pos-manual",))
    assert cursor.fetchone() is not None
    conn.close()


def test_delete_document_cascade_removes_linked_obligation(tmp_path):
    conn = _conn(tmp_path)
    now = int(time.time())
    insert_document(conn, "doc-bill-1", now, title="Tax bill")
    insert_obligation(
        conn,
        "obl1",
        "Property tax",
        "2026-10-01",
        now,
        amount_estimate=2500.0,
        document_id="doc-bill-1",
    )
    conn.commit()

    result = delete_document_cascade(conn, "doc-bill-1")
    conn.commit()

    assert result["obligations_deleted"] == 1
    assert not doc_exist(conn, "doc-bill-1")
    assert not get_obligations_by_document_id(conn, "doc-bill-1")
    conn.close()


@pytest.fixture
def client_with_db(tmp_path):
    db_file = tmp_path / "api.sqlite"
    conn = sqlite3.connect(str(db_file))
    create_db(conn)
    conn.close()
    app.state.use_postgres = False
    app.state.db_path = str(db_file)
    yield TestClient(app)
    app.state.db_path = None


def test_delete_document_api_404(client_with_db):
    res = client_with_db.delete("/documents/missing-doc-id")
    assert res.status_code == 404


def test_delete_document_api_success(client_with_db, tmp_path):
    conn = sqlite3.connect(str(tmp_path / "api.sqlite"))
    now = int(time.time())
    insert_document(conn, "doc-api-1", now, title="To delete")
    conn.commit()
    conn.close()

    res = client_with_db.delete("/documents/doc-api-1")
    assert res.status_code == 204

    conn = sqlite3.connect(str(tmp_path / "api.sqlite"))
    assert not doc_exist(conn, "doc-api-1")
    conn.close()
