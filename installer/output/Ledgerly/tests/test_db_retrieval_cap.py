"""Tests for SQLite retrieval row cap."""

import json
import sqlite3

from app.db import create_db, get_embeddings_for_retrieval, insert_chunk, insert_document, insert_embedding


def test_sqlite_retrieval_cap(monkeypatch, tmp_path):
    monkeypatch.setattr("app.db.SQLITE_RETRIEVAL_MAX_EMBEDDINGS", 3)
    conn = sqlite3.connect(str(tmp_path / "cap.sqlite"))
    create_db(conn)
    now = 1
    for i in range(5):
        doc_id = f"d{i}"
        insert_document(conn, doc_id, now, f"Doc {i}", "src")
        chunk_id = f"{doc_id}:0"
        insert_chunk(conn, chunk_id, doc_id, 0, f"content {i}", 0, 10)
        insert_embedding(conn, chunk_id, "m", json.dumps([float(i)]), 1)
    conn.commit()

    rows = get_embeddings_for_retrieval(conn)
    assert len(rows) == 3
