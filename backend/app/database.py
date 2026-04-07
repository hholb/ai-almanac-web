"""
SQLite-backed storage using stdlib sqlite3.
No ORM, no migrations — simple enough to replace wholesale when we move to Postgres.
"""

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import settings


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def get_db():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id          TEXT PRIMARY KEY,
                external_id TEXT UNIQUE NOT NULL,
                email       TEXT,
                created_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS datasets (
                id          TEXT PRIMARY KEY,
                user_id     TEXT NOT NULL REFERENCES users(id),
                name        TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'pending',
                storage_key TEXT,
                error       TEXT,
                created_at  TEXT NOT NULL,
                ready_at    TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id           TEXT PRIMARY KEY,
                user_id      TEXT NOT NULL,
                dataset_id   TEXT NOT NULL,
                status       TEXT NOT NULL DEFAULT 'queued',
                config_json  TEXT,
                created_at   TEXT NOT NULL,
                started_at   TEXT,
                completed_at TEXT,
                error        TEXT,
                FOREIGN KEY (user_id)    REFERENCES users(id),
                FOREIGN KEY (dataset_id) REFERENCES datasets(id)
            );
        """)


def get_or_create_user(conn: sqlite3.Connection, external_id: str, email: str | None = None) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM users WHERE external_id = ?", (external_id,)).fetchone()
    if row:
        return row
    user_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO users (id, external_id, email, created_at) VALUES (?, ?, ?, ?)",
        (user_id, external_id, email, datetime.now(timezone.utc).isoformat()),
    )
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
