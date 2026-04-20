"""
Database — SQLAlchemy async Core with PostgreSQL via asyncpg.

Connection is configured via DATABASE_URL in settings:
  postgresql+asyncpg://almanac:almanac@localhost:5432/almanac   local dev (compose postgres)
  postgresql://...                                                also accepted; scheme is normalised

In production, DB_PASSWORD is injected separately from Secret Manager and merged
into the URL at engine creation time (Cloud Run can't interpolate a secret value
directly into another env var string).

No ORM — raw SQL via sqlalchemy.text() with named :param placeholders.
"""

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncConnection

from .config import settings


def _make_engine():
    from sqlalchemy.engine import make_url
    url = make_url(settings.database_url)
    # Normalise any postgres driver variant to asyncpg.
    url = url.set(drivername="postgresql+asyncpg")
    if settings.db_password and not url.password:
        url = url.set(password=settings.db_password)
    return create_async_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=1800,  # replace connections older than 30 min
        pool_timeout=10,    # fail fast if pool is exhausted rather than hanging
    )


engine = _make_engine()


@asynccontextmanager
async def get_db():
    """
    Yield a SQLAlchemy AsyncConnection inside a transaction.
    Commits on clean exit, rolls back on exception.
    """
    async with engine.begin() as conn:
        yield conn


async def get_or_create_user(conn: AsyncConnection, external_id: str, email: str | None = None) -> dict:
    row = (await conn.execute(
        text("SELECT * FROM users WHERE external_id = :eid"),
        {"eid": external_id},
    )).mappings().fetchone()
    if row:
        return dict(row)
    user_id = str(uuid.uuid4())
    result = await conn.execute(
        text("INSERT INTO users (id, external_id, email, created_at) VALUES (:id, :eid, :email, :now) RETURNING *"),
        {"id": user_id, "eid": external_id, "email": email, "now": datetime.now(timezone.utc).isoformat()},
    )
    return dict(result.mappings().fetchone())
