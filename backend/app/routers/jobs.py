import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from ..auth import CurrentUser
from ..config import settings, get_model_registry, get_demo_datasets
from ..database import get_db
from ..services.docker_runner import run_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class RompParams(BaseModel):
    """Optional ROMP config knobs. Defaults match generate_config.py."""
    obs: str | None = None
    obs_file_pattern: str | None = None
    obs_var: str | None = None
    model_var: str | None = None
    file_pattern: str | None = None
    region: str | None = None
    wet_threshold: float | None = None
    wet_init: float | None = None
    wet_spell: int | None = None
    dry_spell: int | None = None
    dry_extent: int | None = None
    start_date: str | None = None
    end_date: str | None = None
    start_year_clim: int | None = None
    end_year_clim: int | None = None
    max_forecast_day: int | None = None
    probabilistic: bool | None = None
    members: str | None = None
    parallel: bool | None = None
    ref_model: str | None = None
    init_days: str | None = None
    nc_mask: str | None = None
    ref_model_dir: str | None = None
    thresh_file: str | None = None


class JobCreate(BaseModel):
    dataset_id: str
    model_name: str
    obs_dir: str | None = None
    params: RompParams = RompParams()


class JobOut(BaseModel):
    id: str
    dataset_id: str
    status: str
    model_name: str
    model_dir: str | None = None
    obs_dir: str | None = None
    params: dict | None = None
    created_at: str
    started_at: str | None
    completed_at: str | None
    error: str | None


class ResultFile(BaseModel):
    name: str
    type: str   # "output" | "figure"
    url: str    # relative URL to fetch the file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_job_out(row: dict) -> JobOut:
    cfg = json.loads(row.get("config_json") or "{}")
    return JobOut(
        id=row["id"],
        dataset_id=row["dataset_id"],
        status=row["status"],
        model_name=cfg.get("model_name", ""),
        model_dir=cfg.get("model_dir"),
        obs_dir=cfg.get("obs_dir"),
        params=cfg.get("romp_params") or None,
        created_at=row["created_at"],
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
        error=row.get("error"),
    )


def _resolve_obs_dir(dataset_id: str, obs_dir_override: str | None) -> str:
    if obs_dir_override:
        return obs_dir_override
    # Demo datasets are resolved from config, not the DB.
    if dataset_id.startswith("demo:"):
        demo_map = {d["id"]: d["obs_dir"] for d in get_demo_datasets()}
        obs_dir = demo_map.get(dataset_id)
        if not obs_dir:
            raise HTTPException(status_code=400, detail=f"Unknown demo dataset: {dataset_id!r}")
        return obs_dir
    with get_db() as conn:
        row = conn.execute("SELECT storage_key FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
    if not row or not row["storage_key"]:
        raise HTTPException(status_code=400, detail="Dataset has no storage_key")
    key = row["storage_key"]
    # from-path datasets store the absolute directory directly as storage_key
    if Path(key).is_absolute():
        return key
    # upload-flow datasets store a relative file path — parent dir is the obs dir
    return str((Path(settings.upload_dir) / key).parent)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/models")
async def list_models():
    """Return available model configurations for the UI."""
    return get_model_registry()


@router.post("", response_model=JobOut, status_code=status.HTTP_201_CREATED)
async def create_job(body: JobCreate, user: CurrentUser):
    if body.dataset_id.startswith("demo:"):
        demo_map = {d["id"]: d for d in get_demo_datasets()}
        if body.dataset_id not in demo_map:
            raise HTTPException(status_code=404, detail=f"Unknown demo dataset: {body.dataset_id!r}")
    else:
        def _check_dataset():
            with get_db() as conn:
                row = conn.execute(
                    "SELECT * FROM datasets WHERE id = ? AND user_id = ?",
                    (body.dataset_id, user["id"]),
                ).fetchone()
                return dict(row) if row else None

        ds = await asyncio.to_thread(_check_dataset)
        if not ds:
            raise HTTPException(status_code=404, detail="Dataset not found")
        if ds["status"] != "ready":
            raise HTTPException(status_code=409, detail=f"Dataset is not ready (status: {ds['status']})")

    registry = {m["id"]: m for m in get_model_registry()}
    model_cfg = registry.get(body.model_name)
    if not model_cfg:
        raise HTTPException(status_code=400, detail=f"Unknown model: {body.model_name!r}")

    obs_dir = await asyncio.to_thread(_resolve_obs_dir, body.dataset_id, body.obs_dir)

    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # Start from user-submitted params; inject registry-only fields the frontend
    # doesn't expose (e.g. date_filter_year for fixed IFS/AIFS init schedules).
    romp_params = body.params.model_dump(exclude_none=True)
    for key in ("date_filter_year",):
        if key not in romp_params and model_cfg.get(key) is not None:
            romp_params[key] = model_cfg[key]

    config = {
        "model_name": body.model_name,
        "obs_dir":    obs_dir,
        "model_dir":  model_cfg["model_dir"],
        "romp_params": romp_params,
    }

    def _insert():
        with get_db() as conn:
            conn.execute(
                "INSERT INTO jobs (id, user_id, dataset_id, status, config_json, created_at, started_at) VALUES (?, ?, ?, 'running', ?, ?, ?)",
                (job_id, user["id"], body.dataset_id, json.dumps(config), now, now),
            )
            return dict(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())

    row = await asyncio.to_thread(_insert)
    run_job(job_id, config)
    return _row_to_job_out(row)


@router.get("", response_model=list[JobOut])
async def list_jobs(user: CurrentUser):
    def _list():
        with get_db() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM jobs WHERE user_id = ? ORDER BY created_at DESC",
                (user["id"],),
            ).fetchall()]

    rows = await asyncio.to_thread(_list)
    return [_row_to_job_out(r) for r in rows]


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: str, user: CurrentUser):
    def _get():
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE id = ? AND user_id = ?",
                (job_id, user["id"]),
            ).fetchone()
            return dict(row) if row else None

    row = await asyncio.to_thread(_get)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return _row_to_job_out(row)


@router.get("/{job_id}/logs")
async def get_logs(job_id: str, user: CurrentUser) -> dict:
    def _check():
        with get_db() as conn:
            return conn.execute(
                "SELECT id FROM jobs WHERE id = ? AND user_id = ?", (job_id, user["id"])
            ).fetchone()

    if not await asyncio.to_thread(_check):
        raise HTTPException(status_code=404, detail="Job not found")

    log_path = Path(settings.job_outputs_dir) / job_id / "run.log"
    if not log_path.exists():
        return {"logs": ""}
    return {"logs": await asyncio.to_thread(log_path.read_text)}


@router.get("/{job_id}/results", response_model=list[ResultFile])
async def get_results(job_id: str, user: CurrentUser):
    def _check():
        with get_db() as conn:
            row = conn.execute(
                "SELECT status FROM jobs WHERE id = ? AND user_id = ?", (job_id, user["id"])
            ).fetchone()
            return dict(row) if row else None

    row = await asyncio.to_thread(_check)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    if row["status"] != "complete":
        raise HTTPException(status_code=409, detail=f"Job is not complete (status: {row['status']})")

    def _list_files():
        job_dir = Path(settings.job_outputs_dir) / job_id
        files = []
        for kind in ("output", "figure"):
            d = job_dir / kind
            if d.exists():
                for f in sorted(d.iterdir()):
                    if f.is_file():
                        files.append(ResultFile(
                            name=f.name,
                            type=kind,
                            url=f"/jobs/{job_id}/results/{kind}/{f.name}",
                        ))
        return files

    return await asyncio.to_thread(_list_files)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: str, user: CurrentUser):
    def _delete():
        with get_db() as conn:
            row = conn.execute(
                "SELECT id FROM jobs WHERE id = ? AND user_id = ?", (job_id, user["id"])
            ).fetchone()
            if not row:
                return False
            conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            return True

    found = await asyncio.to_thread(_delete)
    if not found:
        raise HTTPException(status_code=404, detail="Job not found")

    import shutil
    job_dir = Path(settings.job_outputs_dir) / job_id
    if job_dir.exists():
        await asyncio.to_thread(shutil.rmtree, job_dir)


@router.get("/{job_id}/results/{kind}/{filename}")
async def get_result_file(job_id: str, kind: str, filename: str, user: CurrentUser):
    """Serve a result file (figure PNG or output NetCDF/CSV) by URL."""
    if kind not in ("output", "figure"):
        raise HTTPException(status_code=400, detail="kind must be 'output' or 'figure'")

    def _check_job():
        with get_db() as conn:
            return conn.execute(
                "SELECT status FROM jobs WHERE id = ? AND user_id = ?", (job_id, user["id"])
            ).fetchone()

    row = await asyncio.to_thread(_check_job)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    if row["status"] != "complete":
        raise HTTPException(status_code=409, detail=f"Job is not complete (status: {row['status']})")

    file_path = Path(settings.job_outputs_dir) / job_id / kind / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    from fastapi.responses import FileResponse
    return FileResponse(file_path)
