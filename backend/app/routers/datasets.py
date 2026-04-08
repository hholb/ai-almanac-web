import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from ..auth import CurrentUser
from ..config import settings, get_demo_datasets
from ..database import get_db

router = APIRouter(prefix="/datasets", tags=["datasets"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class DatasetOut(BaseModel):
    id: str
    name: str
    status: str
    storage_key: str | None = None
    created_at: str
    ready_at: str | None = None
    error: str | None = None
    is_demo: bool = False


class UploadUrlRequest(BaseModel):
    name: str
    filename: str


class UploadUrlResponse(BaseModel):
    dataset_id: str
    upload_url: str
    storage_key: str


class DatasetFromPathRequest(BaseModel):
    name: str
    obs_dir: str  # absolute path to obs NetCDF directory on the server


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/upload-url", response_model=UploadUrlResponse)
async def request_upload_url(body: UploadUrlRequest, user: CurrentUser, request: Request):
    dataset_id = str(uuid.uuid4())
    storage_key = f"{user['id']}/{dataset_id}/{body.filename}"

    def _insert():
        with get_db() as conn:
            conn.execute(
                "INSERT INTO datasets (id, user_id, name, status, storage_key, created_at) VALUES (?, ?, ?, 'pending', ?, ?)",
                (dataset_id, user["id"], body.name, storage_key, datetime.now(timezone.utc).isoformat()),
            )

    await asyncio.to_thread(_insert)

    upload_url = str(request.base_url) + f"upload/{storage_key}"
    return UploadUrlResponse(dataset_id=dataset_id, upload_url=upload_url, storage_key=storage_key)


@router.post("/{dataset_id}/confirm", response_model=DatasetOut)
async def confirm_upload(dataset_id: str, user: CurrentUser):
    def _confirm():
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM datasets WHERE id = ? AND user_id = ?",
                (dataset_id, user["id"]),
            ).fetchone()
            if not row:
                return None, "not_found"
            if row["status"] != "pending":
                return None, row["status"]
            now = datetime.now(timezone.utc).isoformat()
            conn.execute("UPDATE datasets SET status = 'ready', ready_at = ? WHERE id = ?", (now, dataset_id))
            return dict(conn.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,)).fetchone()), None

    result, err = await asyncio.to_thread(_confirm)
    if err == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
    if err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Dataset is already {err}")
    return DatasetOut(**result)


@router.get("", response_model=list[DatasetOut])
async def list_datasets(user: CurrentUser):
    def _list():
        with get_db() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM datasets WHERE user_id = ? ORDER BY created_at DESC",
                (user["id"],),
            ).fetchall()]

    rows = await asyncio.to_thread(_list)
    user_datasets = [DatasetOut(**r) for r in rows]

    demo_datasets = [
        DatasetOut(
            id=d["id"],
            name=d["name"],
            status="ready",
            created_at="",
            is_demo=True,
        )
        for d in get_demo_datasets()
    ]

    return demo_datasets + user_datasets


@router.post("/from-path", response_model=DatasetOut, status_code=status.HTTP_201_CREATED)
async def dataset_from_path(body: DatasetFromPathRequest, user: CurrentUser):
    """
    Register a local directory as a ready dataset without an upload step.
    Intended for local development and testing — remove or gate behind a
    feature flag before deploying to production.
    """
    from pathlib import Path
    if not Path(body.obs_dir).is_dir():
        raise HTTPException(status_code=400, detail=f"obs_dir does not exist: {body.obs_dir}")

    dataset_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    def _insert():
        with get_db() as conn:
            conn.execute(
                "INSERT INTO datasets (id, user_id, name, status, storage_key, created_at, ready_at) VALUES (?, ?, ?, 'ready', ?, ?, ?)",
                (dataset_id, user["id"], body.name, body.obs_dir, now, now),
            )
            return dict(conn.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,)).fetchone())

    return DatasetOut(**await asyncio.to_thread(_insert))


@router.get("/{dataset_id}", response_model=DatasetOut)
async def get_dataset(dataset_id: str, user: CurrentUser):
    def _get():
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM datasets WHERE id = ? AND user_id = ?",
                (dataset_id, user["id"]),
            ).fetchone()
            return dict(row) if row else None

    row = await asyncio.to_thread(_get)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
    return DatasetOut(**row)
