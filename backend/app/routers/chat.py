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

import asyncio
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
from ..services.chat_state import ChatArtifact, ChatScope, ChatToolCall, ChatTurn
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


class SessionUpdate(BaseModel):
    title: str | None = None


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


def _json_list(value: object) -> list[dict]:
    if isinstance(value, list):
        return value
    return json.loads(value or "[]")


def _json_dict(value: object) -> dict:
    if isinstance(value, dict):
        return value
    return json.loads(value or "{}")


def _replace_turn(transcript: list[dict], turn: ChatTurn) -> list[dict]:
    turn_payload = turn.model_dump(mode="json")
    return [
        turn_payload if existing.get("id") == turn.id else existing
        for existing in transcript
    ]


def _stream_event(event_type: str, **payload: object) -> str:
    return f"data: {json.dumps({'type': event_type, **payload})}\n\n"


def _append_tool_call(turn: ChatTurn, payload: dict) -> None:
    tool_call = ChatToolCall.model_validate(payload)
    if any(existing.id == tool_call.id for existing in turn.tool_calls):
        return
    turn.tool_calls.append(tool_call)


def _append_artifact(turn: ChatTurn, tool_call_id: str | None, payload: dict) -> None:
    artifact = ChatArtifact.model_validate(payload)
    if not any(existing.id == artifact.id for existing in turn.artifacts):
        turn.artifacts.append(artifact)
    if not tool_call_id:
        return
    for tool_call in turn.tool_calls:
        if tool_call.id != tool_call_id:
            continue
        if any(existing.id == artifact.id for existing in tool_call.artifacts):
            return
        tool_call.artifacts.append(artifact)
        return


def _apply_stream_event(turn: ChatTurn, data: dict) -> None:
    event_type = data.get("type")
    if event_type == "text_delta":
        turn.content += data.get("content", "")
        return
    if event_type == "tool_call":
        tool_payload = data.get("tool_call")
        if isinstance(tool_payload, dict):
            _append_tool_call(turn, tool_payload)
        return
    if event_type == "artifact":
        artifact_payload = data.get("artifact")
        if isinstance(artifact_payload, dict):
            _append_artifact(turn, data.get("tool_call_id"), artifact_payload)
        return
    if event_type == "tool_result":
        tool_call_id = data.get("tool_call_id")
        for tool_call in turn.tool_calls:
            if tool_call.id == tool_call_id:
                tool_call.status = data.get("status", tool_call.status)
                tool_call.result = data.get("result")
                return


async def _update_session_state(
    conn,
    session_id: str,
    *,
    provider_state: list[dict],
    transcript: list[dict],
    updated_at: datetime,
) -> None:
    await conn.execute(
        text("""
            UPDATE chat_sessions
            SET provider_state = :provider_state, transcript = :transcript, updated_at = :now
            WHERE id = :id
        """),
        {
            "provider_state": json.dumps(provider_state),
            "transcript": json.dumps(transcript),
            "now": updated_at,
            "id": session_id,
        },
    )


def _classify_stream_error(exc: Exception, assistant_turn: ChatTurn) -> str:
    message = str(exc).lower()
    name = exc.__class__.__name__.lower()
    if "tool" in message or "tool" in name or any(tool.status == "failed" for tool in assistant_turn.tool_calls):
        return "tool_error"
    if "openai" in message or "api" in name or "rate limit" in message or "timeout" in message:
        return "provider_error"
    return "internal_error"


async def _persist_failed_turn(
    conn,
    session_id: str,
    pending_provider_state: list[dict],
    pending_transcript: list[dict],
    assistant_turn: ChatTurn,
    exc: BaseException,
) -> None:
    failed_turn = assistant_turn.model_copy(update={
        "status": "failed",
        "error": str(exc) or exc.__class__.__name__,
    })
    await _update_session_state(
        conn,
        session_id,
        provider_state=pending_provider_state,
        transcript=_replace_turn(pending_transcript, failed_turn),
        updated_at=_now(),
    )


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


@router.patch("/sessions/{session_id}", response_model=SessionOut)
async def update_session(session_id: str, body: SessionUpdate, user: CurrentUser):
    title = body.title.strip() if isinstance(body.title, str) else None
    if title == "":
        title = None

    async with get_db() as conn:
        row = (await conn.execute(
            text("""
                UPDATE chat_sessions
                SET title = :title, updated_at = :now
                WHERE id = :id AND user_id = :uid
                RETURNING *
            """),
            {"id": session_id, "uid": user["id"], "title": title, "now": _now()},
        )).mappings().fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Session not found")

    transcript = row["transcript"] if isinstance(row["transcript"], list) else json.loads(row["transcript"] or "[]")
    scope = row["scope"] if isinstance(row["scope"], dict) else json.loads(row["scope"] or "{}")
    return SessionOut(
        id=row["id"],
        title=row["title"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        message_count=len(transcript),
        scope=ChatScope.model_validate(scope),
    )


@router.post("/sessions/{session_id}/message")
async def send_message(session_id: str, body: MessageIn, user: CurrentUser):
    if not settings.llm_base_url:
        raise HTTPException(status_code=503, detail="LLM is not configured")

    async with get_db() as conn:
        row = (await conn.execute(
            text("SELECT id FROM chat_sessions WHERE id = :id AND user_id = :uid"),
            {"id": session_id, "uid": user["id"]},
        )).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Session not found")

    async def _generate():
        # --- Transaction 1: read state with row lock, persist user + streaming assistant turn ---
        async with get_db() as conn:
            row = (await conn.execute(
                text("""
                    SELECT provider_state, transcript, scope
                    FROM chat_sessions
                    WHERE id = :id AND user_id = :uid
                    FOR UPDATE
                """),
                {"id": session_id, "uid": user["id"]},
            )).mappings().fetchone()
            if not row:
                yield _stream_event("error", error_type="internal_error", message="Session not found")
                return

            provider_state = _json_list(row["provider_state"])
            transcript = _json_list(row["transcript"])
            scope = ChatScope.model_validate(_json_dict(row["scope"]))

            created_at = _now()
            user_turn = ChatTurn(
                id=str(uuid.uuid4()),
                role="user",
                content=body.content,
                created_at=created_at,
            )
            assistant_turn = ChatTurn(
                id=str(uuid.uuid4()),
                role="assistant",
                created_at=created_at,
                status="streaming",
            )

            pending_provider_state = provider_state + [{"role": "user", "content": body.content}]
            pending_transcript = transcript + [
                user_turn.model_dump(mode="json"),
                assistant_turn.model_dump(mode="json"),
            ]
            await _update_session_state(
                conn,
                session_id,
                provider_state=pending_provider_state,
                transcript=pending_transcript,
                updated_at=created_at,
            )
        # --- Transaction 1 committed, lock released ---

        # --- Stream without holding a DB connection ---
        terminal_event: str | None = None
        try:
            async for event in stream_response(pending_provider_state, user["id"], session_id, scope):
                data = json.loads(event)
                if data.get("type") == "done":
                    completed_turn = ChatTurn.model_validate({
                        **assistant_turn.model_dump(mode="json"),
                        **data["turn"],
                        "id": assistant_turn.id,
                        "status": "completed",
                        "error": None,
                    })
                    final_provider_state = data.get("provider_state", pending_provider_state)
                    final_transcript = _replace_turn(pending_transcript, completed_turn)
                    # --- Transaction 2: persist completed state ---
                    async with get_db() as conn:
                        await _update_session_state(
                            conn,
                            session_id,
                            provider_state=final_provider_state,
                            transcript=final_transcript,
                            updated_at=_now(),
                        )
                    hydrated_turn = hydrate_turn_artifact_urls(completed_turn, user["id"])
                    terminal_event = _stream_event("done", turn=hydrated_turn.model_dump(mode="json"))
                    break

                _apply_stream_event(assistant_turn, data)
                yield f"data: {event}\n\n"
            else:
                raise RuntimeError("Chat stream ended without a terminal event")
        except asyncio.CancelledError as exc:
            try:
                async with get_db() as conn:
                    await _persist_failed_turn(
                        conn,
                        session_id,
                        pending_provider_state,
                        pending_transcript,
                        assistant_turn,
                        exc,
                    )
            except Exception:
                pass
            return
        except Exception as exc:
            try:
                async with get_db() as conn:
                    await _persist_failed_turn(
                        conn,
                        session_id,
                        pending_provider_state,
                        pending_transcript,
                        assistant_turn,
                        exc,
                    )
                terminal_event = _stream_event(
                    "error",
                    error_type=_classify_stream_error(exc, assistant_turn),
                    message="Chat response failed",
                )
            except Exception:
                terminal_event = _stream_event(
                    "error",
                    error_type="internal_persistence_error",
                    message="Chat response failed and could not be persisted",
                )
        if terminal_event is not None:
            yield terminal_event

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
