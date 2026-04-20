"""
Chat router — persistent LLM chat sessions with tool access to job data.

Endpoints:
  POST   /chat/sessions              create a new session
  GET    /chat/sessions              list user's sessions
  GET    /chat/sessions/{id}         get session with full message history
  POST   /chat/sessions/{id}/message send a message and stream the response
  DELETE /chat/sessions/{id}         delete a session
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text

from ..auth import CurrentUser
from ..config import settings
from ..database import get_db
from ..services.llm import SYSTEM_PROMPT, stream_response

router = APIRouter(prefix="/chat", tags=["chat"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SessionCreate(BaseModel):
    title: str | None = None
    # Optional job IDs to mention in the opening system context
    job_ids: list[str] = []


class SessionOut(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    id: str
    title: str | None
    created_at: datetime
    updated_at: datetime
    message_count: int


class SessionDetail(SessionOut):
    messages: list[dict]


class MessageIn(BaseModel):
    content: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _build_system_message(job_ids: list[str]) -> dict:
    content = SYSTEM_PROMPT
    if job_ids:
        ids_str = ", ".join(job_ids)
        content += f"\n\nThe user has indicated these job IDs as context for this session: {ids_str}"
    return {"role": "system", "content": content}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(body: SessionCreate, user: CurrentUser):
    if not settings.llm_base_url:
        raise HTTPException(status_code=503, detail="LLM is not configured")

    session_id = str(uuid.uuid4())
    now = _now()
    initial_messages = [_build_system_message(body.job_ids)]

    async with get_db() as conn:
        await conn.execute(
            text("""
                INSERT INTO chat_sessions (id, user_id, title, messages, created_at, updated_at)
                VALUES (:id, :uid, :title, :messages, :now, :now)
            """),
            {
                "id": session_id,
                "uid": user["id"],
                "title": body.title,
                "messages": json.dumps(initial_messages),
                "now": now,
            },
        )

    return SessionOut(
        id=session_id,
        title=body.title,
        created_at=now,
        updated_at=now,
        message_count=0,
    )


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(user: CurrentUser):
    async with get_db() as conn:
        rows = (await conn.execute(
            text("SELECT * FROM chat_sessions WHERE user_id = :uid ORDER BY updated_at DESC"),
            {"uid": user["id"]},
        )).mappings().fetchall()

    result = []
    for r in rows:
        messages = r["messages"] if isinstance(r["messages"], list) else json.loads(r["messages"] or "[]")
        user_msgs = [m for m in messages if m["role"] != "system"]
        result.append(SessionOut(
            id=r["id"],
            title=r["title"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            message_count=len(user_msgs),
        ))
    return result


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(session_id: str, user: CurrentUser):
    async with get_db() as conn:
        row = (await conn.execute(
            text("SELECT * FROM chat_sessions WHERE id = :id AND user_id = :uid"),
            {"id": session_id, "uid": user["id"]},
        )).mappings().fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = row["messages"] if isinstance(row["messages"], list) else json.loads(row["messages"] or "[]")
    visible = [m for m in messages if m["role"] != "system"]
    return SessionDetail(
        id=row["id"],
        title=row["title"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        message_count=len(visible),
        messages=visible,
    )


@router.post("/sessions/{session_id}/message")
async def send_message(session_id: str, body: MessageIn, user: CurrentUser):
    if not settings.llm_base_url:
        raise HTTPException(status_code=503, detail="LLM is not configured")

    async with get_db() as conn:
        row = (await conn.execute(
            text("SELECT messages FROM chat_sessions WHERE id = :id AND user_id = :uid"),
            {"id": session_id, "uid": user["id"]},
        )).mappings().fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Session not found")

    messages: list[dict] = row["messages"] if isinstance(row["messages"], list) else json.loads(row["messages"] or "[]")
    messages.append({"role": "user", "content": body.content})

    async def _generate():
        final_messages: list[dict] | None = None

        async for event in stream_response(messages, user["id"]):
            data = json.loads(event)
            if data["type"] == "done":
                final_messages = data.get("messages")
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
            else:
                yield f"data: {event}\n\n"

        if final_messages is not None:
            async with get_db() as conn:
                await conn.execute(
                    text("UPDATE chat_sessions SET messages = :msgs, updated_at = :now WHERE id = :id"),
                    {"msgs": json.dumps(final_messages), "now": _now(), "id": session_id},
                )

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str, user: CurrentUser):
    async with get_db() as conn:
        row = (await conn.execute(
            text("SELECT id FROM chat_sessions WHERE id = :id AND user_id = :uid"),
            {"id": session_id, "uid": user["id"]},
        )).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")
        await conn.execute(text("DELETE FROM chat_sessions WHERE id = :id"), {"id": session_id})
