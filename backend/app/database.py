"""
Database — SQLAlchemy Core with SQLite (dev) or PostgreSQL (production).

Connection is configured via DATABASE_URL in settings:
  sqlite:///./almanac.db          local development (default)
  postgresql+psycopg2://...       Cloud SQL in production

No ORM — raw SQL via sqlalchemy.text() with named :param placeholders,
which work identically on both backends.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from .config import settings


def _make_engine():
    url = settings.database_url
    if url.startswith("sqlite"):
        return create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_engine(url, pool_pre_ping=True)


engine = _make_engine()


@contextmanager
def get_db():
    """
    Yield a SQLAlchemy connection inside a transaction.
    Commits on clean exit, rolls back on exception.
    """
    with engine.begin() as conn:
        yield conn


def init_db() -> None:
    with get_db() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id          TEXT PRIMARY KEY,
                external_id TEXT UNIQUE NOT NULL,
                email       TEXT,
                created_at  TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS datasets (
                id          TEXT PRIMARY KEY,
                user_id     TEXT NOT NULL REFERENCES users(id),
                name        TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'pending',
                storage_key TEXT,
                error       TEXT,
                created_at  TEXT NOT NULL,
                ready_at    TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS jobs (
                id           TEXT PRIMARY KEY,
                user_id      TEXT NOT NULL REFERENCES users(id),
                dataset_id   TEXT NOT NULL REFERENCES datasets(id),
                status       TEXT NOT NULL DEFAULT 'queued',
                config_json  TEXT,
                created_at   TEXT NOT NULL,
                started_at   TEXT,
                completed_at TEXT,
                error        TEXT
            )
        """))


def get_or_create_user(conn, external_id: str, email: str | None = None) -> dict:
    row = conn.execute(
        text("SELECT * FROM users WHERE external_id = :eid"),
        {"eid": external_id},
    ).mappings().fetchone()
    if row:
        return dict(row)
    user_id = str(uuid.uuid4())
    conn.execute(
        text("INSERT INTO users (id, external_id, email, created_at) VALUES (:id, :eid, :email, :now)"),
        {"id": user_id, "eid": external_id, "email": email, "now": datetime.now(timezone.utc).isoformat()},
    )
    return dict(conn.execute(
        text("SELECT * FROM users WHERE id = :id"), {"id": user_id}
    ).mappings().fetchone())
