"""Tests for GET /documents list including has_openable_original."""

import sqlite3
import tempfile
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import create_db, insert_document
from app.main import app


@pytest.fixture
def client_with_db(tmp_path):
    db_file = tmp_path / "docs_list.sqlite"
    conn = sqlite3.connect(str(db_file))
    create_db(conn)
    conn.close()
    app.state.use_postgres = False
    app.state.db_path = str(db_file)
    yield TestClient(app)
    app.state.db_path = None


def test_get_documents_has_openable_original_when_file_exists(client_with_db, tmp_path):
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"pdf-bytes")
        file_path = f.name
    try:
        conn = sqlite3.connect(str(tmp_path / "docs_list.sqlite"))
        now = int(time.time())
        insert_document(conn, "doc-openable", now, title="Statement", source=file_path)
        conn.commit()
        conn.close()

        res = client_with_db.get("/documents")
        assert res.status_code == 200
        docs = res.json()["documents"]
        match = next(d for d in docs if d["doc_id"] == "doc-openable")
        assert match["has_openable_original"] is True
        assert match["source"] == file_path
    finally:
        Path(file_path).unlink(missing_ok=True)


def test_get_documents_has_openable_original_false_when_missing(client_with_db, tmp_path):
    conn = sqlite3.connect(str(tmp_path / "docs_list.sqlite"))
    now = int(time.time())
    insert_document(conn, "doc-missing", now, title="Gone", source="/no/such/file.pdf")
    conn.commit()
    conn.close()

    res = client_with_db.get("/documents")
    assert res.status_code == 200
    match = next(d for d in res.json()["documents"] if d["doc_id"] == "doc-missing")
    assert match["has_openable_original"] is False
