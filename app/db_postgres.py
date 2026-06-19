"""
Postgres + pgvector implementations for app/db.py entry points.

Used when the connection is a psycopg connection (DATABASE_URL set).
SQL uses %%s placeholders; do not mix with SQLite ? placeholders.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import psycopg

from app.models import RetrievedChunk

logger = logging.getLogger(__name__)

_SCHEMA_STATEMENTS = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    title TEXT,
    source TEXT,
    created_at BIGINT,
    content_hash TEXT,
    facts_learned TEXT,
    original_vault_path TEXT
);

ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_hash TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS facts_learned TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS original_vault_path TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS extracted_position TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS extracted_obligation TEXT;

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT,
    start_offset INTEGER,
    end_offset INTEGER
);

CREATE TABLE IF NOT EXISTS embeddings (
    chunk_id TEXT PRIMARY KEY REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    model TEXT,
    embedding vector(768),
    dim INTEGER
);

CREATE TABLE IF NOT EXISTS document_tags (
    doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    PRIMARY KEY (doc_id, tag)
);

CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT,
    institution TEXT,
    document_id TEXT,
    created_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS positions (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    asset_type TEXT NOT NULL,
    description TEXT,
    principal REAL,
    rate_apr REAL,
    maturity_date TEXT,
    document_id TEXT,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS obligations (
    id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    due_date TEXT NOT NULL,
    amount_estimate REAL,
    priority TEXT,
    document_id TEXT,
    created_at BIGINT NOT NULL
);

ALTER TABLE positions ADD COLUMN IF NOT EXISTS resolved_at BIGINT;
ALTER TABLE obligations ADD COLUMN IF NOT EXISTS resolved_at BIGINT;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS start_date TEXT;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS next_action TEXT;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS liquidity_note TEXT;

CREATE TABLE IF NOT EXISTS ira_overview (
    id TEXT PRIMARY KEY,
    account_name TEXT NOT NULL,
    institution TEXT,
    account_type TEXT,
    balance_estimate REAL,
    rmd_note TEXT,
    next_relevant_date TEXT,
    document_id TEXT,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS trigger_events (
    id TEXT PRIMARY KEY,
    trigger_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    event_date TEXT,
    evaluated_at BIGINT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decision_history (
    id TEXT PRIMARY KEY,
    evaluated_at BIGINT NOT NULL,
    status TEXT NOT NULL,
    memo TEXT,
    trigger_ids TEXT
);

CREATE TABLE IF NOT EXISTS rate_snapshots (
    id TEXT PRIMARY KEY,
    fetched_at BIGINT NOT NULL,
    product_type TEXT NOT NULL,
    term_months INTEGER,
    rate_apr REAL,
    source_url TEXT,
    source_name TEXT,
    quote TEXT
);

CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(content_hash);
CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_doc_id_chunk_index ON chunks(doc_id, chunk_index);
CREATE INDEX IF NOT EXISTS idx_embeddings_model ON embeddings(model);
CREATE INDEX IF NOT EXISTS idx_document_tags_tag ON document_tags(tag);
CREATE INDEX IF NOT EXISTS idx_positions_account_id ON positions(account_id);
CREATE INDEX IF NOT EXISTS idx_positions_maturity ON positions(maturity_date);
CREATE INDEX IF NOT EXISTS idx_obligations_due_date ON obligations(due_date);
CREATE INDEX IF NOT EXISTS idx_trigger_events_evaluated_at ON trigger_events(evaluated_at);
CREATE INDEX IF NOT EXISTS idx_decision_history_evaluated_at ON decision_history(evaluated_at);

CREATE TABLE IF NOT EXISTS ask_history (
    id TEXT PRIMARY KEY,
    job_id TEXT,
    asked_at BIGINT NOT NULL,
    status TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT,
    tables_json TEXT,
    charts_json TEXT,
    route TEXT,
    doc_filter TEXT,
    error TEXT,
    conversation_id TEXT,
    parent_id TEXT,
    related_docs_json TEXT,
    top_chunks_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_ask_history_asked_at ON ask_history(asked_at DESC);
CREATE INDEX IF NOT EXISTS idx_ask_history_conversation_id ON ask_history(conversation_id);
"""


def ensure_postgres_schema(conn: psycopg.Connection) -> None:
    """Create extension, tables, and indexes if missing (local dev / empty DB)."""
    with conn.cursor() as cur:
        for stmt in _SCHEMA_STATEMENTS.split(";"):
            s = stmt.strip()
            if not s:
                continue
            cur.execute(s)
    with conn.cursor() as cur:
        try:
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_embeddings_embedding_hnsw
                ON embeddings USING hnsw (embedding vector_cosine_ops)
                """
            )
        except psycopg.Error as e:
            logger.warning("Could not create HNSW index: %s", e)
    _migrate_ask_history_conversation_columns(conn)


def _migrate_ask_history_conversation_columns(conn: psycopg.Connection) -> None:
    for col, typ in (
        ("conversation_id", "TEXT"),
        ("parent_id", "TEXT"),
        ("related_docs_json", "TEXT"),
        ("top_chunks_json", "TEXT"),
    ):
        with conn.cursor() as cur:
            cur.execute(
                f"ALTER TABLE ask_history ADD COLUMN IF NOT EXISTS {col} {typ}"
            )
    with conn.cursor() as cur:
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_ask_history_conversation_id ON ask_history(conversation_id)"
        )


def _vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(str(float(x)) for x in vec) + "]"


def retrieve_top_k(
    conn: psycopg.Connection,
    query_vec: list[float],
    top_k: int,
    doc_id: str | None = None,
    doc_ids: list[str] | None = None,
) -> list[RetrievedChunk]:
    """
    pgvector cosine distance <=> ; score = 1 - distance (matches unit-vector cosine similarity).
    No row cap — index-backed ORDER BY LIMIT.
    """
    vec_literal = _vector_literal(query_vec)
    where_extra = ""
    params: list[Any] = [vec_literal]

    if doc_ids is not None:
        if len(doc_ids) == 0:
            return []
        ph = ",".join(["%s"] * len(doc_ids))
        where_extra = f" AND c.doc_id IN ({ph})"
        params.extend(doc_ids)
    elif doc_id is not None:
        where_extra = " AND c.doc_id = %s"
        params.append(doc_id)

    params.append(top_k)
    sql = f"""
    SELECT chunk_id, doc_id, content, (1 - dist) AS score
    FROM (
        SELECT e.chunk_id, c.doc_id, c.content, (e.embedding <=> %s::vector) AS dist
        FROM embeddings e
        INNER JOIN chunks c ON e.chunk_id = c.chunk_id
        WHERE e.embedding IS NOT NULL
        {where_extra}
    ) sub
    ORDER BY dist ASC
    LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    out: list[RetrievedChunk] = []
    for chunk_id, did, content, score in rows:
        sc = float(score) if score is not None else 0.0
        text = content or ""
        out.append(
            RetrievedChunk(
                chunk_id=chunk_id,
                doc_id=did,
                score=sc,
                content_snippet=text[:500] if len(text) > 500 else text,
            )
        )
    return out


def insert_document(
    conn: psycopg.Connection,
    doc_id: str,
    created_at: int,
    title: str | None = None,
    source: str | None = None,
    content_hash: str | None = None,
    facts_learned: str | None = None,
    original_vault_path: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO documents(doc_id, title, source, created_at, content_hash, facts_learned, original_vault_path) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (doc_id, title, source, created_at, content_hash, facts_learned, original_vault_path),
        )


def find_doc_id_by_content_hash(conn: psycopg.Connection, content_hash: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT doc_id FROM documents WHERE content_hash = %s LIMIT 1",
            (content_hash,),
        )
        row = cur.fetchone()
    return row[0] if row else None


def insert_chunk(
    conn: psycopg.Connection,
    chunk_id: str,
    doc_id: str,
    chunk_index: int,
    content: str,
    start_offset: int,
    end_offset: int,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO chunks(chunk_id, doc_id, chunk_index, content, start_offset, end_offset) VALUES (%s,%s,%s,%s,%s,%s)",
            (chunk_id, doc_id, chunk_index, content, start_offset, end_offset),
        )


def insert_embedding(
    conn: psycopg.Connection,
    chunk_id: str,
    model: str,
    vector_json: str,
    dim: int,
) -> None:
    vec = json.loads(vector_json)
    literal = _vector_literal(vec)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO embeddings(chunk_id, model, embedding, dim) VALUES (%s,%s,%s::vector,%s)",
            (chunk_id, model, literal, dim),
        )


def doc_exist(conn: psycopg.Connection, doc_id: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM documents WHERE doc_id = %s", (doc_id,))
        return cur.fetchone() is not None


def delete_by_doc_id(conn: psycopg.Connection, doc_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM embeddings WHERE chunk_id IN (SELECT chunk_id FROM chunks WHERE doc_id = %s)",
            (doc_id,),
        )
        cur.execute("DELETE FROM chunks WHERE doc_id = %s", (doc_id,))
        cur.execute("DELETE FROM document_tags WHERE doc_id = %s", (doc_id,))
        cur.execute("DELETE FROM documents WHERE doc_id = %s", (doc_id,))


def delete_positions_by_document_id(conn: psycopg.Connection, doc_id: str) -> int:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM positions WHERE document_id = %s", (doc_id,))
        return cur.rowcount


def delete_obligations_by_document_id(conn: psycopg.Connection, doc_id: str) -> int:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM obligations WHERE document_id = %s", (doc_id,))
        return cur.rowcount


def clear_accounts_linked_to_document(conn: psycopg.Connection, doc_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE accounts SET document_id = NULL WHERE document_id = %s", (doc_id,))


def delete_document_cascade(conn: psycopg.Connection, doc_id: str) -> dict[str, int]:
    positions_deleted = delete_positions_by_document_id(conn, doc_id)
    obligations_deleted = delete_obligations_by_document_id(conn, doc_id)
    clear_accounts_linked_to_document(conn, doc_id)
    delete_by_doc_id(conn, doc_id)
    return {
        "positions_deleted": positions_deleted,
        "obligations_deleted": obligations_deleted,
    }


def set_document_tags(conn: psycopg.Connection, doc_id: str, tags: list[str]) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM document_tags WHERE doc_id = %s", (doc_id,))
        for tag in tags:
            tag = (tag or "").strip()
            if tag:
                cur.execute(
                    "INSERT INTO document_tags(doc_id, tag) VALUES (%s, %s)",
                    (doc_id, tag),
                )


def get_document_tags(conn: psycopg.Connection, doc_id: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT tag FROM document_tags WHERE doc_id = %s ORDER BY tag",
            (doc_id,),
        )
        return [row[0] for row in cur.fetchall()]


def get_document_source(conn: psycopg.Connection, doc_id: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute("SELECT source FROM documents WHERE doc_id = %s", (doc_id,))
        row = cur.fetchone()
        return row[0] if row else None


def get_document_original_vault_path(conn: psycopg.Connection, doc_id: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT original_vault_path FROM documents WHERE doc_id = %s",
            (doc_id,),
        )
        row = cur.fetchone()
        return row[0] if row else None


def update_document_source(conn: psycopg.Connection, doc_id: str, source: str | None) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE documents SET source = %s WHERE doc_id = %s", (source, doc_id))


def get_doc_ids_by_tag(conn: psycopg.Connection, tag: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT doc_id FROM document_tags WHERE tag = %s ORDER BY doc_id",
            (tag.strip(),),
        )
        return [row[0] for row in cur.fetchall()]


def find_doc_ids_by_label_keyword(conn: psycopg.Connection, keyword: str) -> list[str]:
    """Return doc_ids whose title or source contains keyword (case-insensitive)."""
    needle = f"%{keyword.strip().lower()}%"
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT doc_id FROM documents
            WHERE LOWER(COALESCE(title, '')) LIKE %s OR LOWER(COALESCE(source, '')) LIKE %s
            ORDER BY created_at DESC
            """,
            (needle, needle),
        )
        return [row[0] for row in cur.fetchall()]


def get_account_ids_by_document_id(conn: psycopg.Connection, doc_id: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM accounts WHERE document_id = %s ORDER BY name",
            (doc_id,),
        )
        return [row[0] for row in cur.fetchall()]


def set_document_linked_account(
    conn: psycopg.Connection, doc_id: str, account_id: str | None
) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE accounts SET document_id = NULL WHERE document_id = %s", (doc_id,))
        if account_id is not None:
            cur.execute(
                "UPDATE accounts SET document_id = %s WHERE id = %s",
                (doc_id, account_id),
            )


def list_documents(conn: psycopg.Connection, snippet_max_len: int = 250) -> list[tuple]:
    from app.db import _parse_facts_learned

    sql = """
    SELECT
        d.doc_id,
        d.title,
        d.source,
        d.created_at,
        (SELECT COUNT(*) FROM chunks c WHERE c.doc_id = d.doc_id) AS num_chunks,
        (SELECT c.content FROM chunks c WHERE c.doc_id = d.doc_id ORDER BY c.chunk_index LIMIT 1) AS first_content,
        d.facts_learned,
        d.original_vault_path
    FROM documents d
    ORDER BY d.created_at DESC
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    result = []
    for doc_id, title, source, created_at, num_chunks, first_content, facts_raw, original_vault_path in rows:
        snippet = None
        if first_content:
            snippet = first_content[:snippet_max_len] + (
                "..." if len(first_content) > snippet_max_len else ""
            )
        tags = get_document_tags(conn, doc_id)
        linked_account_ids = get_account_ids_by_document_id(conn, doc_id)
        facts_learned = _parse_facts_learned(facts_raw)
        result.append(
            (
                doc_id,
                title,
                source,
                created_at,
                num_chunks,
                snippet,
                tags,
                linked_account_ids,
                facts_learned,
                original_vault_path,
            )
        )
    return result


def insert_account(
    conn: psycopg.Connection,
    id: str,
    name: str,
    created_at: int,
    type: str | None = None,
    institution: str | None = None,
    document_id: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO accounts(id, name, type, institution, document_id, created_at) VALUES (%s,%s,%s,%s,%s,%s)",
            (id, name, type, institution, document_id, created_at),
        )


def list_accounts(conn: psycopg.Connection) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, name, type, institution, document_id, created_at FROM accounts ORDER BY name"
        )
        return cur.fetchall()


def get_account(conn: psycopg.Connection, id: str) -> tuple | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, name, type, institution, document_id, created_at FROM accounts WHERE id = %s",
            (id,),
        )
        return cur.fetchone()


def update_account(
    conn: psycopg.Connection,
    id: str,
    name: str | None = None,
    type: str | None = None,
    institution: str | None = None,
    document_id: str | None = None,
) -> None:
    updates = []
    params = []
    if name is not None:
        updates.append("name = %s")
        params.append(name)
    if type is not None:
        updates.append("type = %s")
        params.append(type)
    if institution is not None:
        updates.append("institution = %s")
        params.append(institution)
    if document_id is not None:
        updates.append("document_id = %s")
        params.append(document_id)
    if not updates:
        return
    params.append(id)
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE accounts SET {', '.join(updates)} WHERE id = %s",
            params,
        )


def delete_account(conn: psycopg.Connection, id: str) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM positions WHERE account_id = %s", (id,))
        cur.execute("DELETE FROM accounts WHERE id = %s", (id,))


_POSITION_SELECT = (
    "id, account_id, asset_type, description, principal, rate_apr, maturity_date, "
    "document_id, created_at, updated_at, start_date, next_action, liquidity_note"
)


def insert_position(
    conn: psycopg.Connection,
    id: str,
    account_id: str,
    asset_type: str,
    created_at: int,
    updated_at: int,
    description: str | None = None,
    principal: float | None = None,
    rate_apr: float | None = None,
    maturity_date: str | None = None,
    document_id: str | None = None,
    start_date: str | None = None,
    next_action: str | None = None,
    liquidity_note: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            f"""INSERT INTO positions(id, account_id, asset_type, description, principal, rate_apr,
               maturity_date, document_id, created_at, updated_at, start_date, next_action, liquidity_note)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                id,
                account_id,
                asset_type,
                description,
                principal,
                rate_apr,
                maturity_date,
                document_id,
                created_at,
                updated_at,
                start_date,
                next_action,
                liquidity_note,
            ),
        )


def list_positions(conn: psycopg.Connection, account_id: str | None = None) -> list[tuple]:
    with conn.cursor() as cur:
        if account_id:
            cur.execute(
                f"SELECT {_POSITION_SELECT} FROM positions WHERE account_id = %s AND resolved_at IS NULL ORDER BY maturity_date",
                (account_id,),
            )
        else:
            cur.execute(
                f"SELECT {_POSITION_SELECT} FROM positions WHERE resolved_at IS NULL ORDER BY maturity_date"
            )
        return cur.fetchall()


def get_position(conn: psycopg.Connection, id: str) -> tuple | None:
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_POSITION_SELECT} FROM positions WHERE id = %s",
            (id,),
        )
        return cur.fetchone()


def update_position(
    conn: psycopg.Connection,
    id: str,
    updated_at: int,
    description: str | None = None,
    principal: float | None = None,
    rate_apr: float | None = None,
    maturity_date: str | None = None,
    document_id: str | None = None,
    start_date: str | None = None,
    next_action: str | None = None,
    liquidity_note: str | None = None,
) -> None:
    updates = ["updated_at = %s"]
    params: list[Any] = [updated_at]
    if description is not None:
        updates.append("description = %s")
        params.append(description)
    if principal is not None:
        updates.append("principal = %s")
        params.append(principal)
    if rate_apr is not None:
        updates.append("rate_apr = %s")
        params.append(rate_apr)
    if maturity_date is not None:
        updates.append("maturity_date = %s")
        params.append(maturity_date)
    if document_id is not None:
        updates.append("document_id = %s")
        params.append(document_id)
    if start_date is not None:
        updates.append("start_date = %s")
        params.append(start_date)
    if next_action is not None:
        updates.append("next_action = %s")
        params.append(next_action)
    if liquidity_note is not None:
        updates.append("liquidity_note = %s")
        params.append(liquidity_note)
    params.append(id)
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE positions SET {', '.join(updates)} WHERE id = %s",
            params,
        )


def delete_position(conn: psycopg.Connection, id: str) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM positions WHERE id = %s", (id,))


def get_positions_by_document_id(conn: psycopg.Connection, doc_id: str) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_POSITION_SELECT} FROM positions WHERE document_id = %s ORDER BY maturity_date",
            (doc_id,),
        )
        return cur.fetchall()


def set_document_extracted_position(conn: psycopg.Connection, doc_id: str, extracted_json: str | None) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE documents SET extracted_position = %s WHERE doc_id = %s", (extracted_json, doc_id))


def list_documents_with_extracted_position(conn: psycopg.Connection) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT doc_id, title, extracted_position FROM documents WHERE extracted_position IS NOT NULL AND TRIM(extracted_position) != '' ORDER BY created_at DESC"
        )
        return cur.fetchall()


def set_document_extracted_obligation(conn: psycopg.Connection, doc_id: str, extracted_json: str | None) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE documents SET extracted_obligation = %s WHERE doc_id = %s", (extracted_json, doc_id))


def list_documents_with_extracted_obligation(conn: psycopg.Connection) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT doc_id, title, extracted_obligation FROM documents WHERE extracted_obligation IS NOT NULL AND TRIM(extracted_obligation) != '' ORDER BY created_at DESC"
        )
        return cur.fetchall()


def insert_obligation(
    conn: psycopg.Connection,
    id: str,
    description: str,
    due_date: str,
    created_at: int,
    amount_estimate: float | None = None,
    priority: str | None = None,
    document_id: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO obligations(id, description, due_date, amount_estimate, priority, document_id, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (id, description, due_date, amount_estimate, priority, document_id, created_at),
        )


def list_obligations(conn: psycopg.Connection) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, description, due_date, amount_estimate, priority, document_id, created_at FROM obligations WHERE resolved_at IS NULL ORDER BY due_date"
        )
        return cur.fetchall()

def list_recent_positions(conn: psycopg.Connection, since_ts: int, limit: int = 10) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, account_id, asset_type, description, principal, rate_apr, maturity_date, document_id, created_at, updated_at
               FROM positions WHERE resolved_at IS NULL AND created_at >= %s ORDER BY created_at DESC LIMIT %s""",
            (since_ts, limit),
        )
        return cur.fetchall()


def list_recent_obligations(conn: psycopg.Connection, since_ts: int, limit: int = 10) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, description, due_date, amount_estimate, priority, document_id, created_at
               FROM obligations WHERE resolved_at IS NULL AND created_at >= %s ORDER BY created_at DESC LIMIT %s""",
            (since_ts, limit),
        )
        return cur.fetchall()


def resolve_position(
    conn: psycopg.Connection, id: str, updated_at: int, maturity_date: str | None = None
) -> None:
    with conn.cursor() as cur:
        if maturity_date is not None:
            cur.execute(
                "UPDATE positions SET maturity_date = %s, updated_at = %s, resolved_at = NULL WHERE id = %s",
                (maturity_date, updated_at, id),
            )
        else:
            cur.execute(
                "UPDATE positions SET resolved_at = %s, updated_at = %s WHERE id = %s",
                (updated_at, updated_at, id),
            )


def resolve_obligation(conn: psycopg.Connection, id: str, resolved_at: int) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE obligations SET resolved_at = %s WHERE id = %s", (resolved_at, id))


def get_obligations_by_document_id(conn: psycopg.Connection, doc_id: str) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, description, due_date, amount_estimate, priority, document_id, created_at FROM obligations WHERE document_id = %s AND resolved_at IS NULL ORDER BY due_date",
            (doc_id,),
        )
        return cur.fetchall()


def get_obligation(conn: psycopg.Connection, id: str) -> tuple | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, description, due_date, amount_estimate, priority, document_id, created_at FROM obligations WHERE id = %s",
            (id,),
        )
        return cur.fetchone()


def update_obligation(
    conn: psycopg.Connection,
    id: str,
    description: str | None = None,
    due_date: str | None = None,
    amount_estimate: float | None = None,
    priority: str | None = None,
    document_id: str | None = None,
) -> None:
    updates = []
    params = []
    if description is not None:
        updates.append("description = %s")
        params.append(description)
    if due_date is not None:
        updates.append("due_date = %s")
        params.append(due_date)
    if amount_estimate is not None:
        updates.append("amount_estimate = %s")
        params.append(amount_estimate)
    if priority is not None:
        updates.append("priority = %s")
        params.append(priority)
    if document_id is not None:
        updates.append("document_id = %s")
        params.append(document_id)
    if not updates:
        return
    params.append(id)
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE obligations SET {', '.join(updates)} WHERE id = %s",
            params,
        )


def delete_obligation(conn: psycopg.Connection, id: str) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM obligations WHERE id = %s", (id,))


def upsert_trigger_event(
    conn: psycopg.Connection,
    id: str,
    trigger_type: str,
    entity_type: str,
    entity_id: str,
    evaluated_at: int,
    status: str,
    event_date: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO trigger_events(id, trigger_type, entity_type, entity_id, event_date, evaluated_at, status)
               VALUES (%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT(id) DO UPDATE SET
                 event_date = EXCLUDED.event_date,
                 evaluated_at = EXCLUDED.evaluated_at,
                 status = EXCLUDED.status""",
            (id, trigger_type, entity_type, entity_id, event_date, evaluated_at, status),
        )


def list_trigger_events(
    conn: psycopg.Connection,
    status: str | None = None,
    since: int | None = None,
    limit: int = 100,
) -> list[tuple]:
    sql = "SELECT id, trigger_type, entity_type, entity_id, event_date, evaluated_at, status FROM trigger_events WHERE 1=1"
    params: list[Any] = []
    if status:
        sql += " AND status = %s"
        params.append(status)
    if since is not None:
        sql += " AND evaluated_at >= %s"
        params.append(since)
    sql += " ORDER BY evaluated_at DESC LIMIT %s"
    params.append(limit)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def insert_decision_history(
    conn: psycopg.Connection,
    id: str,
    evaluated_at: int,
    status: str,
    memo: str | None = None,
    trigger_ids: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO decision_history(id, evaluated_at, status, memo, trigger_ids) VALUES (%s,%s,%s,%s,%s)",
            (id, evaluated_at, status, memo, trigger_ids),
        )


def list_decision_history(
    conn: psycopg.Connection,
    since: int | None = None,
    limit: int = 50,
) -> list[tuple]:
    sql = "SELECT id, evaluated_at, status, memo, trigger_ids FROM decision_history WHERE 1=1"
    params: list[Any] = []
    if since is not None:
        sql += " AND evaluated_at >= %s"
        params.append(since)
    sql += " ORDER BY evaluated_at DESC LIMIT %s"
    params.append(limit)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def insert_ask_history_pending(
    conn: psycopg.Connection,
    id: str,
    job_id: str,
    asked_at: int,
    question: str,
    doc_filter: str | None = None,
    conversation_id: str | None = None,
    parent_id: str | None = None,
) -> None:
    conv_id = conversation_id or id
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO ask_history(
                   id, job_id, asked_at, status, question, doc_filter,
                   conversation_id, parent_id
               ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (id, job_id, asked_at, "pending", question, doc_filter, conv_id, parent_id),
        )
    prune_ask_history(conn)


def insert_ask_history_complete(
    conn: psycopg.Connection,
    id: str,
    asked_at: int,
    question: str,
    answer: str,
    tables_json: str | None = None,
    charts_json: str | None = None,
    route: str | None = None,
    doc_filter: str | None = None,
    conversation_id: str | None = None,
    parent_id: str | None = None,
    related_docs_json: str | None = None,
    top_chunks_json: str | None = None,
) -> None:
    conv_id = conversation_id or id
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO ask_history(
                   id, job_id, asked_at, status, question, answer,
                   tables_json, charts_json, route, doc_filter,
                   conversation_id, parent_id, related_docs_json, top_chunks_json
               ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                id,
                None,
                asked_at,
                "complete",
                question,
                answer,
                tables_json,
                charts_json,
                route,
                doc_filter,
                conv_id,
                parent_id,
                related_docs_json,
                top_chunks_json,
            ),
        )
    prune_ask_history(conn)


def update_ask_history_result(
    conn: psycopg.Connection,
    job_id: str,
    *,
    status: str,
    answer: str | None = None,
    tables_json: str | None = None,
    charts_json: str | None = None,
    route: str | None = None,
    error: str | None = None,
    related_docs_json: str | None = None,
    top_chunks_json: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE ask_history SET status=%s, answer=%s, tables_json=%s, charts_json=%s,
               route=%s, error=%s, related_docs_json=%s, top_chunks_json=%s WHERE job_id=%s""",
            (
                status,
                answer,
                tables_json,
                charts_json,
                route,
                error,
                related_docs_json,
                top_chunks_json,
                job_id,
            ),
        )


def list_ask_history(
    conn: psycopg.Connection,
    limit: int = 50,
) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, job_id, asked_at, status, question, answer,
                      tables_json, charts_json, route, doc_filter, error,
                      conversation_id, parent_id, related_docs_json, top_chunks_json
               FROM ask_history ORDER BY asked_at DESC LIMIT %s""",
            (limit,),
        )
        return cur.fetchall()


def get_document_title(conn: psycopg.Connection, doc_id: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute("SELECT title FROM documents WHERE doc_id = %s", (doc_id,))
        row = cur.fetchone()
    return row[0] if row else None


def get_conversation_doc_filter(conn: psycopg.Connection, conversation_id: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT doc_filter FROM ask_history
               WHERE conversation_id = %s AND parent_id IS NULL
               ORDER BY asked_at ASC LIMIT 1""",
            (conversation_id,),
        )
        row = cur.fetchone()
    return row[0] if row else None


def get_conversation_last_turn_id(conn: psycopg.Connection, conversation_id: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id FROM ask_history
               WHERE conversation_id = %s AND status = 'complete'
               ORDER BY asked_at DESC LIMIT 1""",
            (conversation_id,),
        )
        row = cur.fetchone()
    return row[0] if row else None


def list_conversation_turns(
    conn: psycopg.Connection,
    conversation_id: str,
    limit: int = 50,
) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, job_id, asked_at, status, question, answer,
                      tables_json, charts_json, route, doc_filter, error,
                      conversation_id, parent_id, related_docs_json, top_chunks_json
               FROM ask_history
               WHERE conversation_id = %s
               ORDER BY asked_at ASC
               LIMIT %s""",
            (conversation_id, limit),
        )
        return cur.fetchall()


def prune_ask_history(conn: psycopg.Connection, limit: int = 100) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT COALESCE(conversation_id, id) AS conv_id, COUNT(*) AS cnt
               FROM ask_history
               GROUP BY conv_id
               ORDER BY MAX(asked_at) DESC"""
        )
        rows = cur.fetchall()
    keep_conv_ids: list[str] = []
    total = 0
    for conv_id, cnt in rows:
        if total + cnt > limit and keep_conv_ids:
            break
        keep_conv_ids.append(conv_id)
        total += cnt
    if not keep_conv_ids:
        return
    with conn.cursor() as cur:
        cur.execute(
            """DELETE FROM ask_history
               WHERE COALESCE(conversation_id, id) != ALL(%s)""",
            (keep_conv_ids,),
        )


def insert_ira_overview(
    conn: psycopg.Connection,
    id: str,
    account_name: str,
    created_at: int,
    updated_at: int,
    institution: str | None = None,
    account_type: str | None = None,
    balance_estimate: float | None = None,
    rmd_note: str | None = None,
    next_relevant_date: str | None = None,
    document_id: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO ira_overview(id, account_name, institution, account_type, balance_estimate,
               rmd_note, next_relevant_date, document_id, created_at, updated_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                id,
                account_name,
                institution,
                account_type,
                balance_estimate,
                rmd_note,
                next_relevant_date,
                document_id,
                created_at,
                updated_at,
            ),
        )


def list_ira_overview(conn: psycopg.Connection) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, account_name, institution, account_type, balance_estimate, rmd_note,
               next_relevant_date, document_id, created_at, updated_at
               FROM ira_overview ORDER BY next_relevant_date NULLS LAST, account_name"""
        )
        return cur.fetchall()


def get_ira_overview(conn: psycopg.Connection, id: str) -> tuple | None:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, account_name, institution, account_type, balance_estimate, rmd_note,
               next_relevant_date, document_id, created_at, updated_at FROM ira_overview WHERE id = %s""",
            (id,),
        )
        return cur.fetchone()


def update_ira_overview(
    conn: psycopg.Connection,
    id: str,
    updated_at: int,
    account_name: str | None = None,
    institution: str | None = None,
    account_type: str | None = None,
    balance_estimate: float | None = None,
    rmd_note: str | None = None,
    next_relevant_date: str | None = None,
    document_id: str | None = None,
) -> None:
    updates = ["updated_at = %s"]
    params: list[Any] = [updated_at]
    if account_name is not None:
        updates.append("account_name = %s")
        params.append(account_name)
    if institution is not None:
        updates.append("institution = %s")
        params.append(institution)
    if account_type is not None:
        updates.append("account_type = %s")
        params.append(account_type)
    if balance_estimate is not None:
        updates.append("balance_estimate = %s")
        params.append(balance_estimate)
    if rmd_note is not None:
        updates.append("rmd_note = %s")
        params.append(rmd_note)
    if next_relevant_date is not None:
        updates.append("next_relevant_date = %s")
        params.append(next_relevant_date)
    if document_id is not None:
        updates.append("document_id = %s")
        params.append(document_id)
    params.append(id)
    with conn.cursor() as cur:
        cur.execute(
            f"UPDATE ira_overview SET {', '.join(updates)} WHERE id = %s",
            params,
        )


def delete_ira_overview(conn: psycopg.Connection, id: str) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM ira_overview WHERE id = %s", (id,))


def insert_rate_snapshot(
    conn: psycopg.Connection,
    id: str,
    fetched_at: int,
    product_type: str,
    rate_apr: float,
    term_months: int | None = None,
    source_url: str | None = None,
    source_name: str | None = None,
    quote: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO rate_snapshots(id, fetched_at, product_type, term_months, rate_apr, source_url, source_name, quote)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                id,
                fetched_at,
                product_type,
                term_months,
                rate_apr,
                source_url,
                source_name,
                quote,
            ),
        )


def get_latest_rate_snapshots(
    conn: psycopg.Connection,
    product_type: str | None = None,
    term_months: int | None = None,
    limit: int = 10,
) -> list[tuple]:
    sql = "SELECT id, fetched_at, product_type, term_months, rate_apr, source_url, source_name, quote FROM rate_snapshots WHERE 1=1"
    params: list[Any] = []
    if product_type:
        sql += " AND product_type = %s"
        params.append(product_type)
    if term_months is not None:
        sql += " AND term_months = %s"
        params.append(term_months)
    sql += " ORDER BY fetched_at DESC LIMIT %s"
    params.append(limit)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()
