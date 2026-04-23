from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


def _scope(*, job_ids: list[str] | None = None) -> dict:
    return {
        "kind": "benchmark_run_group",
        "key": "group-1",
        "title": "Group 1",
        "job_ids": job_ids or [],
    }


def _sse_events(body: str) -> list[dict]:
    events: list[dict] = []
    for chunk in body.strip().split("\n\n"):
        if not chunk.startswith("data: "):
            continue
        events.append(json.loads(chunk.removeprefix("data: ")))
    return events


async def _create_session(
    client: httpx.AsyncClient, auth_headers: dict[str, str], *, title: str = "Session"
) -> dict:
    response = await client.post(
        "/chat/sessions",
        headers=auth_headers,
        json={"title": title, "scope": _scope()},
    )
    assert response.status_code == 201
    return response.json()


async def _insert_job(engine: AsyncEngine, user_id: str, job_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO jobs (id, user_id, dataset_id, status, config_json, created_at)
                VALUES (:id, :user_id, :dataset_id, 'completed', '{}'::text, :created_at)
                """
            ),
            {
                "id": job_id,
                "user_id": user_id,
                "dataset_id": f"dataset-{job_id}",
                "created_at": now,
            },
        )


@pytest.mark.asyncio
async def test_chat_session_lifecycle(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    created = await _create_session(client, auth_headers, title="Original title")
    session_id = created["id"]

    list_response = await client.get(
        "/chat/sessions",
        headers=auth_headers,
        params={"scope_kind": "benchmark_run_group", "scope_key": "group-1"},
    )
    assert list_response.status_code == 200
    assert [session["id"] for session in list_response.json()] == [session_id]

    detail_response = await client.get(
        f"/chat/sessions/{session_id}", headers=auth_headers
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["transcript"] == []

    rename_response = await client.patch(
        f"/chat/sessions/{session_id}",
        headers=auth_headers,
        json={"title": "Renamed"},
    )
    assert rename_response.status_code == 200
    assert rename_response.json()["title"] == "Renamed"

    delete_response = await client.delete(
        f"/chat/sessions/{session_id}", headers=auth_headers
    )
    assert delete_response.status_code == 204

    missing_response = await client.get(
        f"/chat/sessions/{session_id}", headers=auth_headers
    )
    assert missing_response.status_code == 404


@pytest.mark.asyncio
async def test_send_message_persists_user_and_assistant_turns(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = await _create_session(client, auth_headers)
    session_id = created["id"]

    async def fake_stream_response(
        provider_state: list[dict],
        user_id: str,
        session_id_arg: str,
        scope: dict,
    ) -> AsyncIterator[str]:
        assert provider_state[-1] == {"role": "user", "content": "How did this run do?"}
        assert session_id_arg == session_id
        yield json.dumps({"type": "text_delta", "content": "It"})
        yield json.dumps(
            {
                "type": "done",
                "turn": {
                    "content": "It finished successfully.",
                    "tool_calls": [],
                    "artifacts": [],
                },
                "provider_state": provider_state
                + [{"role": "assistant", "content": "It finished successfully."}],
            }
        )

    monkeypatch.setattr("app.routers.chat.stream_response", fake_stream_response)

    response = await client.post(
        f"/chat/sessions/{session_id}/message",
        headers=auth_headers,
        json={"content": "How did this run do?"},
    )
    assert response.status_code == 200

    events = _sse_events(response.text)
    assert events[0] == {"type": "text_delta", "content": "It"}
    assert events[-1]["type"] == "done"
    assert events[-1]["turn"]["content"] == "It finished successfully."

    detail_response = await client.get(
        f"/chat/sessions/{session_id}", headers=auth_headers
    )
    transcript = detail_response.json()["transcript"]
    assert [turn["role"] for turn in transcript] == ["user", "assistant"]
    assert transcript[0]["content"] == "How did this run do?"
    assert transcript[1]["content"] == "It finished successfully."
    assert transcript[1]["status"] == "completed"


@pytest.mark.asyncio
async def test_send_message_persists_failed_assistant_turn_on_stream_error(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = await _create_session(client, auth_headers)
    session_id = created["id"]

    async def failing_stream_response(
        provider_state: list[dict],
        user_id: str,
        session_id_arg: str,
        scope: dict,
    ) -> AsyncIterator[str]:
        assert session_id_arg == session_id
        yield json.dumps({"type": "text_delta", "content": "Partial"})
        raise RuntimeError("provider exploded")

    monkeypatch.setattr("app.routers.chat.stream_response", failing_stream_response)

    response = await client.post(
        f"/chat/sessions/{session_id}/message",
        headers=auth_headers,
        json={"content": "Summarize this failure"},
    )
    assert response.status_code == 200

    events = _sse_events(response.text)
    assert events[0] == {"type": "text_delta", "content": "Partial"}
    assert events[-1]["type"] == "error"
    assert events[-1]["message"] == "Chat response failed"

    detail_response = await client.get(
        f"/chat/sessions/{session_id}", headers=auth_headers
    )
    transcript = detail_response.json()["transcript"]
    assert [turn["role"] for turn in transcript] == ["user", "assistant"]
    assert transcript[0]["content"] == "Summarize this failure"
    assert transcript[1]["status"] == "failed"
    assert transcript[1]["content"] == "Partial"
    assert transcript[1]["error"] == "provider exploded"


@pytest.mark.asyncio
async def test_send_message_refreshes_scope_job_ids(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    user_id: str,
    _test_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = await _create_session(client, auth_headers)
    session_id = created["id"]
    job_id = f"job-{uuid4()}"
    await _insert_job(_test_engine, user_id, job_id)

    async def fake_stream_response(
        provider_state: list[dict],
        user_id_arg: str,
        session_id_arg: str,
        scope: dict,
    ) -> AsyncIterator[str]:
        assert session_id_arg == session_id
        assert scope.job_ids == [job_id]
        yield json.dumps(
            {
                "type": "done",
                "turn": {
                    "content": "Scoped response",
                    "tool_calls": [],
                    "artifacts": [],
                },
                "provider_state": provider_state
                + [{"role": "assistant", "content": "Scoped response"}],
            }
        )

    monkeypatch.setattr("app.routers.chat.stream_response", fake_stream_response)

    response = await client.post(
        f"/chat/sessions/{session_id}/message",
        headers=auth_headers,
        json={
            "content": "Use the latest jobs",
            "scope": _scope(job_ids=[job_id, job_id]),
        },
    )
    assert response.status_code == 200
    assert _sse_events(response.text)[-1]["type"] == "done"

    detail_response = await client.get(
        f"/chat/sessions/{session_id}", headers=auth_headers
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["scope"]["job_ids"] == [job_id]


@pytest.mark.asyncio
async def test_run_code_sandbox_preserves_figure_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.chat_state import ChatArtifact, ChatScope
    from app.services.llm import execute_tool

    artifact_bytes = b"fake-webp-bytes"

    class FakeModalFunction:
        def remote(self, code: str) -> dict:
            assert "compute" in code
            return {
                "ok": True,
                "result": {"summary": "created plot"},
                "artifacts": [
                    {
                        "kind": "figure",
                        "filename": "plot.webp",
                        "label": "Plot",
                        "media_type": "image/webp",
                        "data": artifact_bytes,
                    }
                ],
            }

    monkeypatch.setattr("app.config.settings.enable_run_code_sandbox", True)
    monkeypatch.setattr("app.config.settings.modal_token_id", "token-id")
    monkeypatch.setattr("app.config.settings.modal_token_secret", "token-secret")
    monkeypatch.setattr("modal.Function.from_name", lambda *args: FakeModalFunction())

    async def fake_create_chat_figure_artifact(
        session_id: str,
        user_id: str,
        data: bytes,
        *,
        label: str | None = None,
        filename: str | None = None,
        media_type: str | None = None,
    ) -> ChatArtifact:
        assert session_id == "session-1"
        assert user_id == "user-1"
        assert data == artifact_bytes
        return ChatArtifact(
            id="artifact-1",
            kind="figure",
            url="/chat/figures/artifact-1/public?exp=1&sig=test",
            label=label,
            filename=filename,
            media_type=media_type,
            created_at=datetime.now(timezone.utc),
        )

    monkeypatch.setattr(
        "app.services.llm.create_chat_figure_artifact",
        fake_create_chat_figure_artifact,
    )

    result = await execute_tool(
        "run_code_sandbox",
        {"code": "def compute() -> dict:\n    return {}"},
        "user-1",
        ChatScope(key="group-1"),
        "session-1",
    )

    assert result.parsed["ok"] is True
    assert result.parsed["result"] == {"summary": "created plot"}
    assert len(result.parsed["artifacts"]) == 1
    assert result.parsed["artifacts"][0]["id"] == "artifact-1"
    assert result.parsed["artifacts"][0]["label"] == "Plot"
    assert result.parsed["artifacts"][0]["filename"] == "plot.webp"
    assert len(result.artifacts) == 1
    assert result.artifacts[0].id == "artifact-1"
