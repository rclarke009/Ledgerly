"""Database connection helper for FastAPI app state."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

from app.config import DATABASE_URL, DB_PATH


def is_postgres_conn(conn: Any) -> bool:
    mod = type(conn).__module__
    return "psycopg" in mod


@contextmanager
def app_db_connection(app: Any) -> Iterator[Any]:
    if getattr(app.state, "use_postgres", False):
        import psycopg

        conn = psycopg.connect(app.state.pg_dsn)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(app.state.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
