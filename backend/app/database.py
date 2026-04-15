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

from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import NullPool

from .config import settings


def _make_engine():
    from sqlalchemy.engine import make_url
    url = make_url(settings.database_url)
    if url.get_dialect().name == "sqlite":
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=NullPool,
        )
        # WAL mode allows concurrent reads and serialises writes without blocking.
        @event.listens_for(engine, "connect")
        def _set_wal(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA journal_mode=WAL")
        return engine
    # PostgreSQL: inject DB_PASSWORD from Secret Manager if not already in URL.
    # Cloud Run injects it as a separate env var because Terraform can't easily
    # interpolate a secret value into another env var's string.
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
        # Add run_id to existing deployments that predate this column.
        try:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN run_id TEXT"))
        except Exception:
            pass  # column already exists
        # Drop the FK constraint on dataset_id if it exists from an earlier schema.
        # Demo datasets are config-driven and never stored in the datasets table,
        # so the constraint causes an IntegrityError on PostgreSQL for every demo job.
        # The endpoint validates dataset existence before inserting, making the FK redundant.
        try:
            conn.execute(text(
                "ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_dataset_id_fkey"
            ))
        except Exception:
            pass  # SQLite does not support this syntax — safe to ignore


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
