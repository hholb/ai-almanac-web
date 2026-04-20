"""
Database — SQLAlchemy Core with PostgreSQL.

Connection is configured via DATABASE_URL in settings:
  postgresql+psycopg2://almanac:almanac@localhost:5432/almanac   local dev (compose postgres)
  postgresql+psycopg2://...                                       Cloud SQL in production

In production, DB_PASSWORD is injected separately from Secret Manager and merged
into the URL at engine creation time (Cloud Run can't interpolate a secret value
directly into another env var string).

No ORM — raw SQL via sqlalchemy.text() with named :param placeholders.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import create_engine, text

from .config import settings


def _make_engine():
    from sqlalchemy.engine import make_url
    url = make_url(settings.database_url)
    if settings.db_password and not url.password:
        url = url.set(password=settings.db_password)
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
                dataset_id   TEXT NOT NULL,
                status       TEXT NOT NULL DEFAULT 'queued',
                config_json  TEXT,
                run_id       TEXT,
                created_at   TEXT NOT NULL,
                started_at   TEXT,
                completed_at TEXT,
                error        TEXT
            )
        """))
        # Migration shims for deployments that predate these schema changes.
        conn.execute(text("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS run_id TEXT"))
        # Demo datasets are config-driven and not stored in the datasets table,
        # so this FK causes an IntegrityError for every demo job submission.
        conn.execute(text(
            "ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_dataset_id_fkey"
        ))


def get_or_create_user(conn, external_id: str, email: str | None = None) -> dict:
    row = conn.execute(
        text("SELECT * FROM users WHERE external_id = :eid"),
        {"eid": external_id},
    ).mappings().fetchone()
    if row:
        return dict(row)
    user_id = str(uuid.uuid4())
    result = conn.execute(
        text("INSERT INTO users (id, external_id, email, created_at) VALUES (:id, :eid, :email, :now) RETURNING *"),
        {"id": user_id, "eid": external_id, "email": email, "now": datetime.now(timezone.utc).isoformat()},
    )
    row = dict(result.mappings().fetchone())
    result.close()
    return row
