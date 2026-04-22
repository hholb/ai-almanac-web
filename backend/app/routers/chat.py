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

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text

from ..auth import CurrentUser
from ..config import settings
from ..database import get_db
from ..services.chat_artifacts import hydrate_turn_artifact_urls, verify_chat_figure_signature
from ..services.chat_state import ChatScope, ChatTurn
from ..services.llm import SYSTEM_PROMPT, stream_response
from ..services.storage import get_storage, guess_chat_figure_media_type

router = APIRouter(prefix="/chat", tags=["chat"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SessionCreate(BaseModel):
    title: str | None = None
    scope: ChatScope


class SessionOut(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    id: str
    title: str | None
    created_at: datetime
    updated_at: datetime
    message_count: int
    scope: ChatScope


class SessionDetail(SessionOut):
    transcript: list[ChatTurn]


class MessageIn(BaseModel):
    content: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _build_system_message(scope: ChatScope) -> dict:
    content = SYSTEM_PROMPT
    if scope.job_ids:
        ids_str = ", ".join(scope.job_ids)
        content += (
            f"\n\nThis session is scoped to {scope.kind} `{scope.key}`. "
            f"Only use these job IDs unless the scope is explicitly changed: {ids_str}"
        )
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
    initial_messages = [_build_system_message(body.scope)]

    async with get_db() as conn:
        await conn.execute(
            text("""
                INSERT INTO chat_sessions (id, user_id, title, provider_state, scope, transcript, created_at, updated_at)
                VALUES (:id, :uid, :title, :provider_state, :scope, '[]', :now, :now)
            """),
            {
                "id": session_id,
                "uid": user["id"],
                "title": body.title,
                "provider_state": json.dumps(initial_messages),
                "scope": json.dumps(body.scope.model_dump(mode="json")),
                "now": now,
            },
        )

    return SessionOut(
        id=session_id,
        title=body.title,
        created_at=now,
        updated_at=now,
        message_count=0,
        scope=body.scope,
    )


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(
    user: CurrentUser,
    scope_kind: str | None = Query(default=None),
    scope_key: str | None = Query(default=None),
):
    async with get_db() as conn:
        query = "SELECT * FROM chat_sessions WHERE user_id = :uid"
        params: dict[str, object] = {"uid": user["id"]}
        if scope_kind:
            query += " AND scope->>'kind' = :scope_kind"
            params["scope_kind"] = scope_kind
        if scope_key:
            query += " AND scope->>'key' = :scope_key"
            params["scope_key"] = scope_key
        query += " ORDER BY updated_at DESC"
        rows = (await conn.execute(
            text(query),
            params,
        )).mappings().fetchall()

    result = []
    for r in rows:
        transcript = r["transcript"] if isinstance(r["transcript"], list) else json.loads(r["transcript"] or "[]")
        scope = r["scope"] if isinstance(r["scope"], dict) else json.loads(r["scope"] or "{}")
        result.append(SessionOut(
            id=r["id"],
            title=r["title"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            message_count=len(transcript),
            scope=ChatScope.model_validate(scope),
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

    transcript = row["transcript"] if isinstance(row["transcript"], list) else json.loads(row["transcript"] or "[]")
    scope = row["scope"] if isinstance(row["scope"], dict) else json.loads(row["scope"] or "{}")
    return SessionDetail(
        id=row["id"],
        title=row["title"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        message_count=len(transcript),
        scope=ChatScope.model_validate(scope),
        transcript=[hydrate_turn_artifact_urls(ChatTurn.model_validate(turn), user["id"]) for turn in transcript],
    )


@router.post("/sessions/{session_id}/message")
async def send_message(session_id: str, body: MessageIn, user: CurrentUser):
    if not settings.llm_base_url:
        raise HTTPException(status_code=503, detail="LLM is not configured")

    async with get_db() as conn:
        row = (await conn.execute(
            text("SELECT provider_state, transcript, scope FROM chat_sessions WHERE id = :id AND user_id = :uid"),
            {"id": session_id, "uid": user["id"]},
        )).mappings().fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Session not found")

    provider_state: list[dict] = (
        row["provider_state"] if isinstance(row["provider_state"], list)
        else json.loads(row["provider_state"] or "[]")
    )
    transcript: list[dict] = row["transcript"] if isinstance(row["transcript"], list) else json.loads(row["transcript"] or "[]")
    scope_raw = row["scope"] if isinstance(row["scope"], dict) else json.loads(row["scope"] or "{}")
    scope = ChatScope.model_validate(scope_raw)

    user_turn = ChatTurn(
        id=str(uuid.uuid4()),
        role="user",
        content=body.content,
        created_at=_now(),
    )
    provider_state.append({"role": "user", "content": body.content})

    async def _generate():
        final_provider_state: list[dict] | None = None
        assistant_turn: ChatTurn | None = None

        async for event in stream_response(provider_state, user["id"], session_id, scope):
            data = json.loads(event)
            if data["type"] == "done":
                final_provider_state = data.get("provider_state")
                assistant_turn = hydrate_turn_artifact_urls(ChatTurn.model_validate(data["turn"]), user["id"])
                yield f"data: {json.dumps({'type': 'done', 'turn': assistant_turn.model_dump(mode='json')})}\n\n"
            else:
                yield f"data: {event}\n\n"

        if final_provider_state is not None and assistant_turn is not None:
            next_transcript = transcript + [
                user_turn.model_dump(mode="json"),
                assistant_turn.model_dump(mode="json"),
            ]
            async with get_db() as conn:
                await conn.execute(
                    text("""
                        UPDATE chat_sessions
                        SET provider_state = :provider_state, transcript = :transcript, updated_at = :now
                        WHERE id = :id
                    """),
                    {
                        "provider_state": json.dumps(final_provider_state),
                        "transcript": json.dumps(next_transcript),
                        "now": _now(),
                        "id": session_id,
                    },
                )

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _serve_chat_figure(figure_id: str, user_id: str):
    async with get_db() as conn:
        row = (await conn.execute(
            text("""
                SELECT storage_key
                FROM chat_artifacts
                WHERE id = :id AND user_id = :uid AND kind = 'figure'
            """),
            {"id": figure_id, "uid": user_id},
        )).mappings().fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Figure not found")

    storage = get_storage()
    storage_key = row["storage_key"]
    local_path = storage.chat_figure_local_path(storage_key)
    if local_path is not None:
        if not local_path.exists():
            raise HTTPException(status_code=404, detail="Figure not found")
        return FileResponse(local_path, media_type=guess_chat_figure_media_type(local_path))
    redirect_url = storage.chat_figure_redirect_url(storage_key)
    if redirect_url:
        return RedirectResponse(redirect_url)
    raise HTTPException(status_code=404, detail="Figure not found")


@router.get("/figures/{figure_id}")
async def get_chat_figure(figure_id: str, user: CurrentUser):
    return await _serve_chat_figure(figure_id, user["id"])


@router.get("/figures/{figure_id}/public")
async def get_chat_figure_public(figure_id: str, exp: int, sig: str):
    async with get_db() as conn:
        row = (await conn.execute(
            text("SELECT user_id FROM chat_artifacts WHERE id = :id AND kind = 'figure'"),
            {"id": figure_id},
        )).mappings().fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Figure not found")
    user_id = row["user_id"]
    if not verify_chat_figure_signature(figure_id, user_id, exp, sig):
        raise HTTPException(status_code=403, detail="Invalid figure signature")
    return await _serve_chat_figure(figure_id, user_id)


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
