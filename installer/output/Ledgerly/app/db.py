## 4. Database schema and a small DB layer

# Design the SQLite schema: tables for **documents** 
# (e.g. `doc_id`, `title`, `source`, `created_at`), 
# **chunks** (e.g. `chunk_id`, `doc_id`, `chunk_index`, 
# `content`, `start_offset`, `end_offset`), and **embeddings** 
# (e.g. `chunk_id`, `model`, `vector_json`, `dim`). 
# 
# Add indexes that support “get chunks by doc_id” and 
# “get embedding by chunk_id.” Implement a thin DB module 
# that opens the DB, creates tables if they don’t exist, 
# and exposes a few helpers (e.g. insert document, insert chunks, 
# insert embeddings, fetch embeddings for retrieval). 
# Keep it synchronous and simple unless you already know you want async.

# can use app.state.dbconn for db conn since we will create that in main right before we call create db

import sqlite3
import json
from typing import Any

from app.config import SQLITE_RETRIEVAL_MAX_EMBEDDINGS
from app.db_connection import is_postgres_conn


def create_db(conn: Any) -> Any:
    if is_postgres_conn(conn):
        from app import db_postgres

        db_postgres.ensure_postgres_schema(conn)
        conn.commit()
        return conn
    #conn = app.state.dbconn    # sqlite3.connect("documentsdb.sqlite")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            doc_id TEXT PRIMARY KEY,
            title TEXT,
            source TEXT,
            created_at INTEGER,
            content_hash TEXT,
            facts_learned TEXT
        )
    """)
    try:
        conn.execute("ALTER TABLE documents ADD COLUMN content_hash TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE documents ADD COLUMN facts_learned TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE documents ADD COLUMN original_vault_path TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE documents ADD COLUMN extracted_position TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE documents ADD COLUMN extracted_obligation TEXT")
    except sqlite3.OperationalError:
        pass
    conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(content_hash)")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS chunks (
        chunk_id TEXT PRIMARY KEY,
        doc_id TEXT,
        chunk_index INTEGER,
        content TEXT,
        start_offset INTEGER,
        end_offset INTEGER
        )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS embeddings (
        chunk_id TEXT PRIMARY KEY,
        model TEXT,
        vector_json TEXT,
        dim INTEGER
        )
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_chunks_doc_id_chunk_index ON chunks(doc_id, chunk_index)
    """)

    # Financial tables (Private Cash Assistant)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT,
            institution TEXT,
            document_id TEXT,
            created_at INTEGER NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            asset_type TEXT NOT NULL,
            description TEXT,
            principal REAL,
            rate_apr REAL,
            maturity_date TEXT,
            document_id TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            FOREIGN KEY (account_id) REFERENCES accounts(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS obligations (
            id TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            due_date TEXT NOT NULL,
            amount_estimate REAL,
            priority TEXT,
            document_id TEXT,
            created_at INTEGER NOT NULL
        )
    """)
    try:
        conn.execute("ALTER TABLE positions ADD COLUMN resolved_at INTEGER")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE obligations ADD COLUMN resolved_at INTEGER")
    except sqlite3.OperationalError:
        pass
    for col, typ in (
        ("start_date", "TEXT"),
        ("next_action", "TEXT"),
        ("liquidity_note", "TEXT"),
    ):
        try:
            conn.execute(f"ALTER TABLE positions ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ira_overview (
            id TEXT PRIMARY KEY,
            account_name TEXT NOT NULL,
            institution TEXT,
            account_type TEXT,
            balance_estimate REAL,
            rmd_note TEXT,
            next_relevant_date TEXT,
            document_id TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trigger_events (
            id TEXT PRIMARY KEY,
            trigger_type TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            event_date TEXT,
            evaluated_at INTEGER NOT NULL,
            status TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS decision_history (
            id TEXT PRIMARY KEY,
            evaluated_at INTEGER NOT NULL,
            status TEXT NOT NULL,
            memo TEXT,
            trigger_ids TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rate_snapshots (
            id TEXT PRIMARY KEY,
            fetched_at INTEGER NOT NULL,
            product_type TEXT NOT NULL,
            term_months INTEGER,
            rate_apr REAL,
            source_url TEXT,
            source_name TEXT,
            quote TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_positions_account_id ON positions(account_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_positions_maturity ON positions(maturity_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_obligations_due_date ON obligations(due_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trigger_events_evaluated_at ON trigger_events(evaluated_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_decision_history_evaluated_at ON decision_history(evaluated_at)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ask_history (
            id TEXT PRIMARY KEY,
            job_id TEXT,
            asked_at INTEGER NOT NULL,
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
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ask_history_asked_at ON ask_history(asked_at)")
    for col, typ in (
        ("conversation_id", "TEXT"),
        ("parent_id", "TEXT"),
        ("related_docs_json", "TEXT"),
        ("top_chunks_json", "TEXT"),
    ):
        try:
            conn.execute(f"ALTER TABLE ask_history ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ask_history_conversation_id ON ask_history(conversation_id)"
    )

    conn.execute("""
        CREATE TABLE IF NOT EXISTS document_tags (
            doc_id TEXT NOT NULL,
            tag TEXT NOT NULL,
            PRIMARY KEY (doc_id, tag),
            FOREIGN KEY (doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_document_tags_tag ON document_tags(tag)")

    conn.commit()

    return conn

# CRUD

def insert_document(conn,
    doc_id: str,
    created_at: int,
    title: str | None = None,
    source: str | None = None,
    content_hash: str | None = None,
    facts_learned: str | None = None,
    original_vault_path: str | None = None,
    ) -> None:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.insert_document(
            conn, doc_id, created_at, title, source, content_hash, facts_learned,
            original_vault_path,
        )
    conn.execute(
        "INSERT INTO documents(doc_id, title, source, created_at, content_hash, facts_learned, original_vault_path) VALUES (?,?,?,?,?,?,?)",
        (doc_id, title, source, created_at, content_hash, facts_learned, original_vault_path),
    )


def find_doc_id_by_content_hash(conn: sqlite3.Connection, content_hash: str) -> str | None:
    """Return doc_id of an existing document with the same content hash, or None."""
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.find_doc_id_by_content_hash(conn, content_hash)
    cursor = conn.execute(
        "SELECT doc_id FROM documents WHERE content_hash = ? LIMIT 1",
        (content_hash,),
    )
    row = cursor.fetchone()
    return row[0] if row else None


def insert_chunk(conn: sqlite3.Connection, 
    chunk_id: str,
    doc_id: str,
    chunk_index: int,
    content: str,
    start_offset: int,
    end_offset: int
    ) -> None:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.insert_chunk(
            conn, chunk_id, doc_id, chunk_index, content, start_offset, end_offset
        )
    conn.execute("INSERT INTO chunks(chunk_id, doc_id, chunk_index, content, start_offset, end_offset) VALUES (?,?,?,?,?,?)", (chunk_id, doc_id, chunk_index, content, start_offset, end_offset),)
    # conn.commit()

def insert_embedding(conn: sqlite3.Connection, 
    chunk_id: str,
    model: str,
    vector_json: str,
    dim: int
    ) -> None:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.insert_embedding(conn, chunk_id, model, vector_json, dim)
    conn.execute("INSERT INTO embeddings(chunk_id, model, vector_json, dim) VALUES (?,?,?,?)", (chunk_id, model, vector_json, dim),)
    # conn.commit()

def doc_exist(
    conn: sqlite3.Connection,
    doc_id: str
    )->None:
    '''returns none if doc does not exist.  if it's a duplicate, raises 409'''
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.doc_exist(conn, doc_id)
    cursor = conn.execute("SELECT 1 FROM documents WHERE doc_id = ?", (doc_id,))
    return cursor.fetchone() is not None        # returns True if it finds one?

def get_embeddings_for_retrieval(conn, doc_id=None, doc_ids=None) -> list[tuple]:
    if is_postgres_conn(conn):
        raise RuntimeError(
            "get_embeddings_for_retrieval is SQLite-only; Postgres uses pgvector in retrieve_top_k"
        )
    sql = """
    SELECT e.chunk_id, c.doc_id, e.vector_json, c.content
    FROM embeddings e
    JOIN chunks c ON e.chunk_id = c.chunk_id
    """
    if doc_ids is not None:
        if len(doc_ids) == 0:
            return []
        placeholders = ",".join("?" * len(doc_ids))
        cursor = conn.execute(sql + " WHERE c.doc_id IN (" + placeholders + ")", doc_ids)
    elif doc_id is not None:
        cursor = conn.execute(sql + " WHERE c.doc_id = ?", (doc_id,))
    else:
        if SQLITE_RETRIEVAL_MAX_EMBEDDINGS > 0:
            sql += " LIMIT ?"
            cursor = conn.execute(sql, (SQLITE_RETRIEVAL_MAX_EMBEDDINGS,))
        else:
            cursor = conn.execute(sql)
    rows = cursor.fetchall()
    return [
        (chunk_id, doc_id, json.loads(vector_json), content)
        for chunk_id, doc_id, vector_json, content in rows
    ]


def delete_by_doc_id(conn: sqlite3.Connection, doc_id: str) -> None:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.delete_by_doc_id(conn, doc_id)
    conn.execute("DELETE FROM embeddings WHERE chunk_id IN (SELECT chunk_id FROM chunks WHERE doc_id = ?)", (doc_id,))
    conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
    conn.execute("DELETE FROM document_tags WHERE doc_id = ?", (doc_id,))
    conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))


def delete_positions_by_document_id(conn: sqlite3.Connection, doc_id: str) -> int:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.delete_positions_by_document_id(conn, doc_id)
    cursor = conn.execute("DELETE FROM positions WHERE document_id = ?", (doc_id,))
    return cursor.rowcount


def delete_obligations_by_document_id(conn: sqlite3.Connection, doc_id: str) -> int:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.delete_obligations_by_document_id(conn, doc_id)
    cursor = conn.execute("DELETE FROM obligations WHERE document_id = ?", (doc_id,))
    return cursor.rowcount


def clear_accounts_linked_to_document(conn: sqlite3.Connection, doc_id: str) -> None:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.clear_accounts_linked_to_document(conn, doc_id)
    conn.execute("UPDATE accounts SET document_id = NULL WHERE document_id = ?", (doc_id,))


def delete_document_cascade(conn: sqlite3.Connection, doc_id: str) -> dict[str, int]:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.delete_document_cascade(conn, doc_id)
    positions_deleted = delete_positions_by_document_id(conn, doc_id)
    obligations_deleted = delete_obligations_by_document_id(conn, doc_id)
    clear_accounts_linked_to_document(conn, doc_id)
    delete_by_doc_id(conn, doc_id)
    return {
        "positions_deleted": positions_deleted,
        "obligations_deleted": obligations_deleted,
    }


def set_document_tags(conn: sqlite3.Connection, doc_id: str, tags: list[str]) -> None:
    """Replace all tags for a document with the given list."""
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.set_document_tags(conn, doc_id, tags)
    conn.execute("DELETE FROM document_tags WHERE doc_id = ?", (doc_id,))
    for tag in tags:
        tag = (tag or "").strip()
        if tag:
            conn.execute("INSERT INTO document_tags(doc_id, tag) VALUES (?, ?)", (doc_id, tag))


def get_document_tags(conn: sqlite3.Connection, doc_id: str) -> list[str]:
    """Return list of tag strings for a document."""
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.get_document_tags(conn, doc_id)
    cursor = conn.execute("SELECT tag FROM document_tags WHERE doc_id = ? ORDER BY tag", (doc_id,))
    return [row[0] for row in cursor.fetchall()]


def get_document_source(conn: sqlite3.Connection, doc_id: str) -> str | None:
    """Return documents.source for doc_id, or None if missing."""
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.get_document_source(conn, doc_id)
    cursor = conn.execute("SELECT source FROM documents WHERE doc_id = ?", (doc_id,))
    row = cursor.fetchone()
    return row[0] if row else None


def get_document_original_vault_path(conn: sqlite3.Connection, doc_id: str) -> str | None:
    """Return stored vault-relative path for the original copy, if any."""
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.get_document_original_vault_path(conn, doc_id)
    cursor = conn.execute(
        "SELECT original_vault_path FROM documents WHERE doc_id = ?", (doc_id,)
    )
    row = cursor.fetchone()
    return row[0] if row else None


def update_document_source(conn: sqlite3.Connection, doc_id: str, source: str | None) -> None:
    """Set documents.source (use None to clear)."""
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.update_document_source(conn, doc_id, source)
    conn.execute("UPDATE documents SET source = ? WHERE doc_id = ?", (source, doc_id))


def get_doc_ids_by_tag(conn: sqlite3.Connection, tag: str) -> list[str]:
    """Return list of doc_ids that have the given tag."""
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.get_doc_ids_by_tag(conn, tag)
    cursor = conn.execute("SELECT doc_id FROM document_tags WHERE tag = ? ORDER BY doc_id", (tag.strip(),))
    return [row[0] for row in cursor.fetchall()]


def find_doc_ids_by_label_keyword(conn: sqlite3.Connection, keyword: str) -> list[str]:
    """Return doc_ids whose title or source contains keyword (case-insensitive)."""
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.find_doc_ids_by_label_keyword(conn, keyword)
    needle = f"%{keyword.strip().lower()}%"
    cursor = conn.execute(
        """
        SELECT doc_id FROM documents
        WHERE LOWER(COALESCE(title, '')) LIKE ? OR LOWER(COALESCE(source, '')) LIKE ?
        ORDER BY created_at DESC
        """,
        (needle, needle),
    )
    return [row[0] for row in cursor.fetchall()]


def get_account_ids_by_document_id(conn: sqlite3.Connection, doc_id: str) -> list[str]:
    """Return list of account IDs that have document_id = doc_id."""
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.get_account_ids_by_document_id(conn, doc_id)
    cursor = conn.execute("SELECT id FROM accounts WHERE document_id = ? ORDER BY name", (doc_id,))
    return [row[0] for row in cursor.fetchall()]


def set_document_linked_account(
    conn: sqlite3.Connection, doc_id: str, account_id: str | None
) -> None:
    """Set which account links to this document. Clear all accounts with this doc_id, then set the given account's document_id if non-null."""
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.set_document_linked_account(conn, doc_id, account_id)
    conn.execute("UPDATE accounts SET document_id = NULL WHERE document_id = ?", (doc_id,))
    if account_id is not None:
        conn.execute("UPDATE accounts SET document_id = ? WHERE id = ?", (doc_id, account_id))


def _parse_facts_learned(raw: str | None) -> list[str] | None:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    out: list[str] = []
    for item in data:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out if out else None


def list_documents(conn: sqlite3.Connection, snippet_max_len: int = 250) -> list[tuple]:
    """
    Returns list of (doc_id, title, source, created_at, num_chunks, snippet, tags, linked_account_ids, facts_learned, original_vault_path).
    snippet is first chunk content truncated to snippet_max_len; None if no chunks.
    tags is list of tag strings; linked_account_ids is list of account IDs that reference this doc.
    facts_learned is list of strings or None.
    Ordered by created_at desc.
    """
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.list_documents(conn, snippet_max_len)
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
    cursor = conn.execute(sql)
    rows = cursor.fetchall()
    result = []
    for doc_id, title, source, created_at, num_chunks, first_content, facts_raw, original_vault_path in rows:
        snippet = None
        if first_content:
            snippet = first_content[:snippet_max_len] + ("..." if len(first_content) > snippet_max_len else "")
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


# --- Financial (accounts, positions, obligations, triggers, decision_history) ---

def insert_account(
    conn: sqlite3.Connection,
    id: str,
    name: str,
    created_at: int,
    type: str | None = None,
    institution: str | None = None,
    document_id: str | None = None,
) -> None:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.insert_account(
            conn, id, name, created_at, type, institution, document_id
        )
    conn.execute(
        "INSERT INTO accounts(id, name, type, institution, document_id, created_at) VALUES (?,?,?,?,?,?)",
        (id, name, type, institution, document_id, created_at),
    )


def list_accounts(conn: sqlite3.Connection) -> list[tuple]:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.list_accounts(conn)
    cursor = conn.execute(
        "SELECT id, name, type, institution, document_id, created_at FROM accounts ORDER BY name"
    )
    return cursor.fetchall()


def get_account(conn: sqlite3.Connection, id: str) -> tuple | None:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.get_account(conn, id)
    cursor = conn.execute(
        "SELECT id, name, type, institution, document_id, created_at FROM accounts WHERE id = ?",
        (id,),
    )
    return cursor.fetchone()


def update_account(
    conn: sqlite3.Connection,
    id: str,
    name: str | None = None,
    type: str | None = None,
    institution: str | None = None,
    document_id: str | None = None,
) -> None:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.update_account(
            conn, id, name, type, institution, document_id
        )
    updates = []
    params = []
    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if type is not None:
        updates.append("type = ?")
        params.append(type)
    if institution is not None:
        updates.append("institution = ?")
        params.append(institution)
    if document_id is not None:
        updates.append("document_id = ?")
        params.append(document_id)
    if not updates:
        return
    params.append(id)
    conn.execute(f"UPDATE accounts SET {', '.join(updates)} WHERE id = ?", params)


def delete_account(conn: sqlite3.Connection, id: str) -> None:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.delete_account(conn, id)
    conn.execute("DELETE FROM positions WHERE account_id = ?", (id,))
    conn.execute("DELETE FROM accounts WHERE id = ?", (id,))


_POSITION_SELECT = (
    "id, account_id, asset_type, description, principal, rate_apr, maturity_date, "
    "document_id, created_at, updated_at, start_date, next_action, liquidity_note"
)


def insert_position(
    conn: sqlite3.Connection,
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
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.insert_position(
            conn,
            id,
            account_id,
            asset_type,
            created_at,
            updated_at,
            description,
            principal,
            rate_apr,
            maturity_date,
            document_id,
            start_date,
            next_action,
            liquidity_note,
        )
    conn.execute(
        f"""INSERT INTO positions(id, account_id, asset_type, description, principal, rate_apr,
           maturity_date, document_id, created_at, updated_at, start_date, next_action, liquidity_note)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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


def list_positions(conn: sqlite3.Connection, account_id: str | None = None) -> list[tuple]:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.list_positions(conn, account_id)
    if account_id:
        cursor = conn.execute(
            f"SELECT {_POSITION_SELECT} FROM positions WHERE account_id = ? AND resolved_at IS NULL ORDER BY maturity_date",
            (account_id,),
        )
    else:
        cursor = conn.execute(
            f"SELECT {_POSITION_SELECT} FROM positions WHERE resolved_at IS NULL ORDER BY maturity_date"
        )
    return cursor.fetchall()


def get_position(conn: sqlite3.Connection, id: str) -> tuple | None:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.get_position(conn, id)
    cursor = conn.execute(
        f"SELECT {_POSITION_SELECT} FROM positions WHERE id = ?",
        (id,),
    )
    return cursor.fetchone()


def update_position(
    conn: sqlite3.Connection,
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
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.update_position(
            conn,
            id,
            updated_at,
            description,
            principal,
            rate_apr,
            maturity_date,
            document_id,
            start_date,
            next_action,
            liquidity_note,
        )
    updates = ["updated_at = ?"]
    params = [updated_at]
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    if principal is not None:
        updates.append("principal = ?")
        params.append(principal)
    if rate_apr is not None:
        updates.append("rate_apr = ?")
        params.append(rate_apr)
    if maturity_date is not None:
        updates.append("maturity_date = ?")
        params.append(maturity_date)
    if document_id is not None:
        updates.append("document_id = ?")
        params.append(document_id)
    if start_date is not None:
        updates.append("start_date = ?")
        params.append(start_date)
    if next_action is not None:
        updates.append("next_action = ?")
        params.append(next_action)
    if liquidity_note is not None:
        updates.append("liquidity_note = ?")
        params.append(liquidity_note)
    params.append(id)
    conn.execute(f"UPDATE positions SET {', '.join(updates)} WHERE id = ?", params)


def delete_position(conn: sqlite3.Connection, id: str) -> None:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.delete_position(conn, id)
    conn.execute("DELETE FROM positions WHERE id = ?", (id,))


def get_positions_by_document_id(conn: sqlite3.Connection, doc_id: str) -> list[tuple]:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.get_positions_by_document_id(conn, doc_id)
    cursor = conn.execute(
        f"SELECT {_POSITION_SELECT} FROM positions WHERE document_id = ? ORDER BY maturity_date",
        (doc_id,),
    )
    return cursor.fetchall()


def set_document_extracted_position(conn: sqlite3.Connection, doc_id: str, extracted_json: str | None) -> None:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.set_document_extracted_position(conn, doc_id, extracted_json)
    conn.execute("UPDATE documents SET extracted_position = ? WHERE doc_id = ?", (extracted_json, doc_id))


def clear_document_extracted_position(conn: sqlite3.Connection, doc_id: str) -> None:
    set_document_extracted_position(conn, doc_id, None)


def list_documents_with_extracted_position(conn: sqlite3.Connection) -> list[tuple]:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.list_documents_with_extracted_position(conn)
    cursor = conn.execute(
        "SELECT doc_id, title, extracted_position FROM documents WHERE extracted_position IS NOT NULL AND TRIM(extracted_position) != '' ORDER BY created_at DESC"
    )
    return cursor.fetchall()


def insert_obligation(
    conn: sqlite3.Connection,
    id: str,
    description: str,
    due_date: str,
    created_at: int,
    amount_estimate: float | None = None,
    priority: str | None = None,
    document_id: str | None = None,
) -> None:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.insert_obligation(
            conn,
            id,
            description,
            due_date,
            created_at,
            amount_estimate,
            priority,
            document_id,
        )
    conn.execute(
        """INSERT INTO obligations(id, description, due_date, amount_estimate, priority, document_id, created_at)
           VALUES (?,?,?,?,?,?,?)""",
        (id, description, due_date, amount_estimate, priority, document_id, created_at),
    )


def list_obligations(conn: sqlite3.Connection) -> list[tuple]:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.list_obligations(conn)
    cursor = conn.execute(
        "SELECT id, description, due_date, amount_estimate, priority, document_id, created_at FROM obligations WHERE resolved_at IS NULL ORDER BY due_date"
    )
    return cursor.fetchall()


def list_recent_positions(conn: sqlite3.Connection, since_ts: int, limit: int = 10) -> list[tuple]:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.list_recent_positions(conn, since_ts, limit)
    cursor = conn.execute(
        """SELECT id, account_id, asset_type, description, principal, rate_apr, maturity_date, document_id, created_at, updated_at
           FROM positions WHERE resolved_at IS NULL AND created_at >= ? ORDER BY created_at DESC LIMIT ?""",
        (since_ts, limit),
    )
    return cursor.fetchall()


def list_recent_obligations(conn: sqlite3.Connection, since_ts: int, limit: int = 10) -> list[tuple]:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.list_recent_obligations(conn, since_ts, limit)
    cursor = conn.execute(
        """SELECT id, description, due_date, amount_estimate, priority, document_id, created_at
           FROM obligations WHERE resolved_at IS NULL AND created_at >= ? ORDER BY created_at DESC LIMIT ?""",
        (since_ts, limit),
    )
    return cursor.fetchall()


def resolve_position(conn: sqlite3.Connection, id: str, updated_at: int, maturity_date: str | None = None) -> None:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.resolve_position(conn, id, updated_at, maturity_date)
    if maturity_date is not None:
        conn.execute(
            "UPDATE positions SET maturity_date = ?, updated_at = ?, resolved_at = NULL WHERE id = ?",
            (maturity_date, updated_at, id),
        )
    else:
        conn.execute(
            "UPDATE positions SET resolved_at = ?, updated_at = ? WHERE id = ?",
            (updated_at, updated_at, id),
        )


def resolve_obligation(conn: sqlite3.Connection, id: str, resolved_at: int) -> None:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.resolve_obligation(conn, id, resolved_at)
    conn.execute("UPDATE obligations SET resolved_at = ? WHERE id = ?", (resolved_at, id))


def get_obligations_by_document_id(conn: sqlite3.Connection, doc_id: str) -> list[tuple]:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.get_obligations_by_document_id(conn, doc_id)
    cursor = conn.execute(
        "SELECT id, description, due_date, amount_estimate, priority, document_id, created_at FROM obligations WHERE document_id = ? AND resolved_at IS NULL ORDER BY due_date",
        (doc_id,),
    )
    return cursor.fetchall()


def set_document_extracted_obligation(conn: sqlite3.Connection, doc_id: str, extracted_json: str | None) -> None:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.set_document_extracted_obligation(conn, doc_id, extracted_json)
    conn.execute("UPDATE documents SET extracted_obligation = ? WHERE doc_id = ?", (extracted_json, doc_id))


def clear_document_extracted_obligation(conn: sqlite3.Connection, doc_id: str) -> None:
    set_document_extracted_obligation(conn, doc_id, None)


def list_documents_with_extracted_obligation(conn: sqlite3.Connection) -> list[tuple]:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.list_documents_with_extracted_obligation(conn)
    cursor = conn.execute(
        "SELECT doc_id, title, extracted_obligation FROM documents WHERE extracted_obligation IS NOT NULL AND TRIM(extracted_obligation) != '' ORDER BY created_at DESC"
    )
    return cursor.fetchall()


def get_obligation(conn: sqlite3.Connection, id: str) -> tuple | None:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.get_obligation(conn, id)
    cursor = conn.execute(
        "SELECT id, description, due_date, amount_estimate, priority, document_id, created_at FROM obligations WHERE id = ?",
        (id,),
    )
    return cursor.fetchone()


def update_obligation(
    conn: sqlite3.Connection,
    id: str,
    description: str | None = None,
    due_date: str | None = None,
    amount_estimate: float | None = None,
    priority: str | None = None,
    document_id: str | None = None,
) -> None:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.update_obligation(
            conn,
            id,
            description,
            due_date,
            amount_estimate,
            priority,
            document_id,
        )
    updates = []
    params = []
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    if due_date is not None:
        updates.append("due_date = ?")
        params.append(due_date)
    if amount_estimate is not None:
        updates.append("amount_estimate = ?")
        params.append(amount_estimate)
    if priority is not None:
        updates.append("priority = ?")
        params.append(priority)
    if document_id is not None:
        updates.append("document_id = ?")
        params.append(document_id)
    if not updates:
        return
    params.append(id)
    conn.execute(f"UPDATE obligations SET {', '.join(updates)} WHERE id = ?", params)


def delete_obligation(conn: sqlite3.Connection, id: str) -> None:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.delete_obligation(conn, id)
    conn.execute("DELETE FROM obligations WHERE id = ?", (id,))


def upsert_trigger_event(
    conn: sqlite3.Connection,
    id: str,
    trigger_type: str,
    entity_type: str,
    entity_id: str,
    evaluated_at: int,
    status: str,
    event_date: str | None = None,
) -> None:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.upsert_trigger_event(
            conn,
            id,
            trigger_type,
            entity_type,
            entity_id,
            evaluated_at,
            status,
            event_date,
        )
    conn.execute(
        """INSERT INTO trigger_events(id, trigger_type, entity_type, entity_id, event_date, evaluated_at, status)
           VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET event_date=excluded.event_date, evaluated_at=excluded.evaluated_at, status=excluded.status""",
        (id, trigger_type, entity_type, entity_id, event_date, evaluated_at, status),
    )


def list_trigger_events(
    conn: sqlite3.Connection,
    status: str | None = None,
    since: int | None = None,
    limit: int = 100,
) -> list[tuple]:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.list_trigger_events(conn, status, since, limit)
    sql = "SELECT id, trigger_type, entity_type, entity_id, event_date, evaluated_at, status FROM trigger_events WHERE 1=1"
    params = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if since is not None:
        sql += " AND evaluated_at >= ?"
        params.append(since)
    sql += " ORDER BY evaluated_at DESC LIMIT ?"
    params.append(limit)
    cursor = conn.execute(sql, params)
    return cursor.fetchall()


def insert_decision_history(
    conn: sqlite3.Connection,
    id: str,
    evaluated_at: int,
    status: str,
    memo: str | None = None,
    trigger_ids: str | None = None,
) -> None:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.insert_decision_history(
            conn, id, evaluated_at, status, memo, trigger_ids
        )
    conn.execute(
        "INSERT INTO decision_history(id, evaluated_at, status, memo, trigger_ids) VALUES (?,?,?,?,?)",
        (id, evaluated_at, status, memo, trigger_ids),
    )


def list_decision_history(
    conn: sqlite3.Connection,
    since: int | None = None,
    limit: int = 50,
) -> list[tuple]:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.list_decision_history(conn, since, limit)
    sql = "SELECT id, evaluated_at, status, memo, trigger_ids FROM decision_history WHERE 1=1"
    params = []
    if since is not None:
        sql += " AND evaluated_at >= ?"
        params.append(since)
    sql += " ORDER BY evaluated_at DESC LIMIT ?"
    params.append(limit)
    cursor = conn.execute(sql, params)
    return cursor.fetchall()


ASK_HISTORY_RETENTION_LIMIT = 100


def insert_ask_history_pending(
    conn: sqlite3.Connection,
    id: str,
    job_id: str,
    asked_at: int,
    question: str,
    doc_filter: str | None = None,
    conversation_id: str | None = None,
    parent_id: str | None = None,
) -> None:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.insert_ask_history_pending(
            conn,
            id,
            job_id,
            asked_at,
            question,
            doc_filter,
            conversation_id=conversation_id,
            parent_id=parent_id,
        )
    conv_id = conversation_id or id
    conn.execute(
        """INSERT INTO ask_history(
               id, job_id, asked_at, status, question, doc_filter,
               conversation_id, parent_id
           ) VALUES (?,?,?,?,?,?,?,?)""",
        (id, job_id, asked_at, "pending", question, doc_filter, conv_id, parent_id),
    )
    _prune_ask_history(conn)


def insert_ask_history_complete(
    conn: sqlite3.Connection,
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
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.insert_ask_history_complete(
            conn,
            id,
            asked_at,
            question,
            answer,
            tables_json,
            charts_json,
            route,
            doc_filter,
            conversation_id=conversation_id,
            parent_id=parent_id,
            related_docs_json=related_docs_json,
            top_chunks_json=top_chunks_json,
        )
    conv_id = conversation_id or id
    conn.execute(
        """INSERT INTO ask_history(
               id, job_id, asked_at, status, question, answer,
               tables_json, charts_json, route, doc_filter,
               conversation_id, parent_id, related_docs_json, top_chunks_json
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
    _prune_ask_history(conn)


def update_ask_history_result(
    conn: sqlite3.Connection,
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
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.update_ask_history_result(
            conn,
            job_id,
            status=status,
            answer=answer,
            tables_json=tables_json,
            charts_json=charts_json,
            route=route,
            error=error,
            related_docs_json=related_docs_json,
            top_chunks_json=top_chunks_json,
        )
    conn.execute(
        """UPDATE ask_history SET status=?, answer=?, tables_json=?, charts_json=?,
           route=?, error=?, related_docs_json=?, top_chunks_json=? WHERE job_id=?""",
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
    conn: sqlite3.Connection,
    limit: int = 50,
) -> list[tuple]:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.list_ask_history(conn, limit=limit)
    cursor = conn.execute(
        """SELECT id, job_id, asked_at, status, question, answer,
                  tables_json, charts_json, route, doc_filter, error,
                  conversation_id, parent_id, related_docs_json, top_chunks_json
           FROM ask_history ORDER BY asked_at DESC LIMIT ?""",
        (limit,),
    )
    return cursor.fetchall()


def get_document_title(conn: sqlite3.Connection, doc_id: str) -> str | None:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.get_document_title(conn, doc_id)
    row = conn.execute(
        "SELECT title FROM documents WHERE doc_id = ?", (doc_id,)
    ).fetchone()
    return row[0] if row else None


def get_conversation_doc_filter(conn: sqlite3.Connection, conversation_id: str) -> str | None:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.get_conversation_doc_filter(conn, conversation_id)
    row = conn.execute(
        """SELECT doc_filter FROM ask_history
           WHERE conversation_id = ? AND parent_id IS NULL
           ORDER BY asked_at ASC LIMIT 1""",
        (conversation_id,),
    ).fetchone()
    return row[0] if row else None


def get_conversation_last_turn_id(conn: sqlite3.Connection, conversation_id: str) -> str | None:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.get_conversation_last_turn_id(conn, conversation_id)
    row = conn.execute(
        """SELECT id FROM ask_history
           WHERE conversation_id = ? AND status = 'complete'
           ORDER BY asked_at DESC LIMIT 1""",
        (conversation_id,),
    ).fetchone()
    return row[0] if row else None


def list_conversation_turns(
    conn: sqlite3.Connection,
    conversation_id: str,
    limit: int = 50,
) -> list[tuple]:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.list_conversation_turns(conn, conversation_id, limit=limit)
    cursor = conn.execute(
        """SELECT id, job_id, asked_at, status, question, answer,
                  tables_json, charts_json, route, doc_filter, error,
                  conversation_id, parent_id, related_docs_json, top_chunks_json
           FROM ask_history
           WHERE conversation_id = ?
           ORDER BY asked_at ASC
           LIMIT ?""",
        (conversation_id, limit),
    )
    return cursor.fetchall()


def _prune_ask_history(conn: sqlite3.Connection) -> None:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.prune_ask_history(conn)
    rows = conn.execute(
        """SELECT COALESCE(conversation_id, id) AS conv_id, COUNT(*) AS cnt
           FROM ask_history
           GROUP BY conv_id
           ORDER BY MAX(asked_at) DESC"""
    ).fetchall()
    keep_conv_ids: list[str] = []
    total = 0
    for conv_id, cnt in rows:
        if total + cnt > ASK_HISTORY_RETENTION_LIMIT and keep_conv_ids:
            break
        keep_conv_ids.append(conv_id)
        total += cnt
    if not keep_conv_ids:
        return
    placeholders = ",".join("?" * len(keep_conv_ids))
    conn.execute(
        f"""DELETE FROM ask_history
            WHERE COALESCE(conversation_id, id) NOT IN ({placeholders})""",
        keep_conv_ids,
    )


def insert_ira_overview(
    conn: sqlite3.Connection,
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
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.insert_ira_overview(
            conn,
            id,
            account_name,
            created_at,
            updated_at,
            institution,
            account_type,
            balance_estimate,
            rmd_note,
            next_relevant_date,
            document_id,
        )
    conn.execute(
        """INSERT INTO ira_overview(id, account_name, institution, account_type, balance_estimate,
           rmd_note, next_relevant_date, document_id, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
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


def list_ira_overview(conn: sqlite3.Connection) -> list[tuple]:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.list_ira_overview(conn)
    cursor = conn.execute(
        """SELECT id, account_name, institution, account_type, balance_estimate, rmd_note,
           next_relevant_date, document_id, created_at, updated_at
           FROM ira_overview ORDER BY next_relevant_date, account_name"""
    )
    return cursor.fetchall()


def get_ira_overview(conn: sqlite3.Connection, id: str) -> tuple | None:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.get_ira_overview(conn, id)
    cursor = conn.execute(
        """SELECT id, account_name, institution, account_type, balance_estimate, rmd_note,
           next_relevant_date, document_id, created_at, updated_at FROM ira_overview WHERE id = ?""",
        (id,),
    )
    return cursor.fetchone()


def update_ira_overview(
    conn: sqlite3.Connection,
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
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.update_ira_overview(
            conn,
            id,
            updated_at,
            account_name,
            institution,
            account_type,
            balance_estimate,
            rmd_note,
            next_relevant_date,
            document_id,
        )
    updates = ["updated_at = ?"]
    params: list[Any] = [updated_at]
    if account_name is not None:
        updates.append("account_name = ?")
        params.append(account_name)
    if institution is not None:
        updates.append("institution = ?")
        params.append(institution)
    if account_type is not None:
        updates.append("account_type = ?")
        params.append(account_type)
    if balance_estimate is not None:
        updates.append("balance_estimate = ?")
        params.append(balance_estimate)
    if rmd_note is not None:
        updates.append("rmd_note = ?")
        params.append(rmd_note)
    if next_relevant_date is not None:
        updates.append("next_relevant_date = ?")
        params.append(next_relevant_date)
    if document_id is not None:
        updates.append("document_id = ?")
        params.append(document_id)
    params.append(id)
    conn.execute(f"UPDATE ira_overview SET {', '.join(updates)} WHERE id = ?", params)


def delete_ira_overview(conn: sqlite3.Connection, id: str) -> None:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.delete_ira_overview(conn, id)
    conn.execute("DELETE FROM ira_overview WHERE id = ?", (id,))


def insert_rate_snapshot(
    conn: sqlite3.Connection,
    id: str,
    fetched_at: int,
    product_type: str,
    rate_apr: float,
    term_months: int | None = None,
    source_url: str | None = None,
    source_name: str | None = None,
    quote: str | None = None,
) -> None:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.insert_rate_snapshot(
            conn,
            id,
            fetched_at,
            product_type,
            rate_apr,
            term_months,
            source_url,
            source_name,
            quote,
        )
    conn.execute(
        """INSERT INTO rate_snapshots(id, fetched_at, product_type, term_months, rate_apr, source_url, source_name, quote)
           VALUES (?,?,?,?,?,?,?,?)""",
        (id, fetched_at, product_type, term_months, rate_apr, source_url, source_name, quote),
    )


def get_latest_rate_snapshots(
    conn: sqlite3.Connection,
    product_type: str | None = None,
    term_months: int | None = None,
    limit: int = 10,
) -> list[tuple]:
    if is_postgres_conn(conn):
        from app import db_postgres

        return db_postgres.get_latest_rate_snapshots(
            conn, product_type, term_months, limit
        )
    sql = "SELECT id, fetched_at, product_type, term_months, rate_apr, source_url, source_name, quote FROM rate_snapshots WHERE 1=1"
    params = []
    if product_type:
        sql += " AND product_type = ?"
        params.append(product_type)
    if term_months is not None:
        sql += " AND term_months = ?"
        params.append(term_months)
    sql += " ORDER BY fetched_at DESC LIMIT ?"
    params.append(limit)
    cursor = conn.execute(sql, params)
    return cursor.fetchall()
