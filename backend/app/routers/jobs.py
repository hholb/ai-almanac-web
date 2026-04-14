import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import text

from ..auth import CurrentUser
from ..config import settings, get_model_registry, get_demo_datasets
from ..database import get_db
from ..services.runner import get_runner
from ..services.storage import get_storage

router = APIRouter(prefix="/jobs", tags=["jobs"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class RompParams(BaseModel):
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
    url: str


class MetricStats(BaseModel):
    mean: float
    min: float
    max: float
    p25: float
    p50: float
    p75: float
    p90: float
    unit: str


class WindowMetrics(BaseModel):
    window: str
    model: str
    tolerance_days: int | None
    metrics: dict[str, MetricStats]


class GridInfo(BaseModel):
    lats: list[float]
    lons: list[float]


class JobMetrics(BaseModel):
    job_id: str
    windows: list[WindowMetrics]
    grid: GridInfo | None = None
    bbox: dict | None = None


class JobGridResponse(BaseModel):
    job_id: str
    model: str
    window: str
    metric: str
    lats: list[float]
    lons: list[float]
    values: list[list[float | None]]
    unit: str
    min: float
    max: float


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
    if dataset_id.startswith("demo:"):
        demo_map = {d["id"]: d["obs_dir"] for d in get_demo_datasets()}
        obs_dir = demo_map.get(dataset_id)
        if not obs_dir:
            raise HTTPException(status_code=400, detail=f"Unknown demo dataset: {dataset_id!r}")
        return obs_dir
    with get_db() as conn:
        row = conn.execute(
            text("SELECT storage_key FROM datasets WHERE id = :id"), {"id": dataset_id}
        ).mappings().fetchone()
    if not row or not row["storage_key"]:
        raise HTTPException(status_code=400, detail="Dataset has no storage_key")
    return get_storage().resolve_obs_path(row["storage_key"])


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/models")
async def list_models():
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
                    text("SELECT * FROM datasets WHERE id = :id AND user_id = :uid"),
                    {"id": body.dataset_id, "uid": user["id"]},
                ).mappings().fetchone()
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

    romp_params = body.params.model_dump(exclude_none=True)
    for key in ("date_filter_year", "probabilistic", "members"):
        if key not in romp_params and model_cfg.get(key) is not None:
            romp_params[key] = model_cfg[key]

    if "obs_file_pattern" not in romp_params and body.dataset_id.startswith("demo:"):
        demo_map = {d["id"]: d for d in get_demo_datasets()}
        demo = demo_map.get(body.dataset_id)
        if demo and demo.get("obs_file_pattern"):
            romp_params["obs_file_pattern"] = demo["obs_file_pattern"]

    config = {
        "model_name": body.model_name,
        "obs_dir":    obs_dir,
        "model_dir":  model_cfg["model_dir"],
        "romp_params": romp_params,
    }

    def _insert():
        with get_db() as conn:
            return dict(conn.execute(
                text("INSERT INTO jobs (id, user_id, dataset_id, status, config_json, created_at, started_at) "
                     "VALUES (:id, :uid, :did, 'running', :cfg, :now, :now) RETURNING *"),
                {"id": job_id, "uid": user["id"], "did": body.dataset_id,
                 "cfg": json.dumps(config), "now": now},
            ).mappings().fetchone())

    row = await asyncio.to_thread(_insert)
    get_runner().run_job(job_id, config)
    return _row_to_job_out(row)


@router.get("", response_model=list[JobOut])
async def list_jobs(user: CurrentUser):
    def _list():
        with get_db() as conn:
            return [dict(r) for r in conn.execute(
                text("SELECT * FROM jobs WHERE user_id = :uid ORDER BY created_at DESC"),
                {"uid": user["id"]},
            ).mappings().fetchall()]

    rows = await asyncio.to_thread(_list)
    return [_row_to_job_out(r) for r in rows]


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: str, user: CurrentUser):
    def _get():
        with get_db() as conn:
            row = conn.execute(
                text("SELECT * FROM jobs WHERE id = :id AND user_id = :uid"),
                {"id": job_id, "uid": user["id"]},
            ).mappings().fetchone()
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
                text("SELECT id FROM jobs WHERE id = :id AND user_id = :uid"),
                {"id": job_id, "uid": user["id"]},
            ).fetchone()

    if not await asyncio.to_thread(_check):
        raise HTTPException(status_code=404, detail="Job not found")

    logs = await asyncio.to_thread(get_storage().read_log, job_id)
    return {"logs": logs}


@router.get("/{job_id}/results", response_model=list[ResultFile])
async def get_results(job_id: str, user: CurrentUser):
    def _check():
        with get_db() as conn:
            row = conn.execute(
                text("SELECT status FROM jobs WHERE id = :id AND user_id = :uid"),
                {"id": job_id, "uid": user["id"]},
            ).mappings().fetchone()
            return dict(row) if row else None

    row = await asyncio.to_thread(_check)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    if row["status"] != "complete":
        raise HTTPException(status_code=409, detail=f"Job is not complete (status: {row['status']})")

    storage = get_storage()
    files = await asyncio.to_thread(storage.list_result_files, job_id)
    return [
        ResultFile(
            name=filename,
            type=kind,
            url=storage.generate_result_url(job_id, kind, filename),
        )
        for kind, filename in files
    ]


@router.get("/{job_id}/results/{kind}/{filename}")
async def get_result_file(job_id: str, kind: str, filename: str, user: CurrentUser):
    """Serve a result file — FileResponse locally, signed URL redirect in production."""
    if kind not in ("output", "figure"):
        raise HTTPException(status_code=400, detail="kind must be 'output' or 'figure'")

    def _check_job():
        with get_db() as conn:
            return conn.execute(
                text("SELECT status FROM jobs WHERE id = :id AND user_id = :uid"),
                {"id": job_id, "uid": user["id"]},
            ).mappings().fetchone()

    row = await asyncio.to_thread(_check_job)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    if row["status"] != "complete":
        raise HTTPException(status_code=409, detail=f"Job is not complete (status: {row['status']})")

    storage = get_storage()
    local_path = storage.result_file_path(job_id, kind, filename)

    if local_path is not None:
        # Local dev: serve directly
        if not local_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        from fastapi.responses import FileResponse
        return FileResponse(local_path)
    else:
        # GCS: redirect to a signed URL
        signed_url = await asyncio.to_thread(storage.generate_result_url, job_id, kind, filename)
        return RedirectResponse(url=signed_url, status_code=302)


@router.get("/{job_id}/metrics", response_model=JobMetrics)
async def get_metrics(
    job_id: str,
    user: CurrentUser,
    lat_min: float | None = None,
    lat_max: float | None = None,
    lon_min: float | None = None,
    lon_max: float | None = None,
):
    def _check():
        with get_db() as conn:
            row = conn.execute(
                text("SELECT status FROM jobs WHERE id = :id AND user_id = :uid"),
                {"id": job_id, "uid": user["id"]},
            ).mappings().fetchone()
            return dict(row) if row else None

    row = await asyncio.to_thread(_check)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    if row["status"] != "complete":
        raise HTTPException(status_code=409, detail=f"Job is not complete (status: {row['status']})")

    bbox = (lat_min, lat_max, lon_min, lon_max)
    has_bbox = any(v is not None for v in bbox)

    def _compute():
        try:
            import numpy as np
            import xarray as xr
        except ImportError:
            raise HTTPException(status_code=503, detail="xarray not available on this server")

        storage = get_storage()

        # For GCS, we need to open the files via fsspec. For local, use the path directly.
        if storage.is_local:
            from ..services.storage import LocalStorage
            output_dir = storage._outputs_dir / job_id / "output"
            nc_files = sorted(output_dir.glob("spatial_metrics_*.nc")) if output_dir.exists() else []
        else:
            import gcsfs
            fs = gcsfs.GCSFileSystem()
            prefix = f"{storage._outputs_bucket}/{job_id}/output/spatial_metrics_"
            nc_files = sorted(fs.glob(f"{prefix}*.nc"))
            nc_files = [f"gs://{f}" for f in nc_files]

        UNIT_MAP = {"false_alarm_rate": "fraction", "miss_rate": "fraction"}
        windows = []
        grid_info: GridInfo | None = None
        actual_bbox: dict | None = None

        def _open_nc(path):
            if storage.is_local:
                return xr.open_dataset(path)
            with fs.open(path.removeprefix("gs://"), "rb") as f:
                return xr.load_dataset(f)

        for nc_file in nc_files:
            ds = _open_nc(nc_file)

            if grid_info is None and "lat" in ds.coords and "lon" in ds.coords:
                grid_info = GridInfo(
                    lats=[float(v) for v in sorted(ds.lat.values)],
                    lons=[float(v) for v in sorted(ds.lon.values)],
                )

            if has_bbox:
                lats = ds.lat.values
                lons = ds.lon.values
                if lat_min is not None: lats = lats[lats >= lat_min]
                if lat_max is not None: lats = lats[lats <= lat_max]
                if lon_min is not None: lons = lons[lons >= lon_min]
                if lon_max is not None: lons = lons[lons <= lon_max]
                ds = ds.sel(lat=lats, lon=lons)

            if actual_bbox is None and "lat" in ds.coords and "lon" in ds.coords:
                lats = ds.lat.values
                lons = ds.lon.values
                if len(lats) and len(lons):
                    actual_bbox = {
                        "lat_min": float(lats.min()), "lat_max": float(lats.max()),
                        "lon_min": float(lons.min()), "lon_max": float(lons.max()),
                    }

            model = str(ds.attrs.get("model", ""))
            window_label = str(ds.attrs.get("verification_window", "")).replace(",", "-")
            tolerance_days = int(ds.attrs["tolerance_days"]) if "tolerance_days" in ds.attrs else None

            metrics: dict[str, MetricStats] = {}
            for var in ds.data_vars:
                arr = ds[var].values.astype(float)
                valid = arr[~np.isnan(arr)]
                if len(valid) == 0:
                    continue
                var_str = str(var)
                unit = UNIT_MAP.get(var_str, "days")
                metrics[var_str] = MetricStats(
                    mean=float(np.mean(valid)),
                    min=float(np.min(valid)),
                    max=float(np.max(valid)),
                    p25=float(np.percentile(valid, 25)),
                    p50=float(np.percentile(valid, 50)),
                    p75=float(np.percentile(valid, 75)),
                    p90=float(np.percentile(valid, 90)),
                    unit=unit,
                )
            ds.close()
            windows.append(WindowMetrics(
                window=window_label,
                model=model,
                tolerance_days=tolerance_days,
                metrics=metrics,
            ))

        windows.sort(key=lambda w: (w.model == "climatology", w.window))
        return JobMetrics(job_id=job_id, windows=windows, grid=grid_info, bbox=actual_bbox)

    return await asyncio.to_thread(_compute)


@router.get("/{job_id}/grid", response_model=JobGridResponse)
async def get_grid(
    job_id: str,
    user: CurrentUser,
    model: str,
    window: str,
    metric: str,
):
    def _check():
        with get_db() as conn:
            row = conn.execute(
                text("SELECT status FROM jobs WHERE id = :id AND user_id = :uid"),
                {"id": job_id, "uid": user["id"]},
            ).mappings().fetchone()
            return dict(row) if row else None

    row = await asyncio.to_thread(_check)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    if row["status"] != "complete":
        raise HTTPException(status_code=409, detail=f"Job is not complete (status: {row['status']})")

    def _load():
        try:
            import numpy as np
            import xarray as xr
        except ImportError:
            raise HTTPException(status_code=503, detail="xarray not available")

        storage = get_storage()
        w_alt = window.replace("-", ",")

        if storage.is_local:
            output_dir = storage._outputs_dir / job_id / "output"
            matches = list(output_dir.glob(f"spatial_metrics_{model}_{window}.nc"))
            if not matches:
                matches = list(output_dir.glob(f"spatial_metrics_{model}_{w_alt}.nc"))
        else:
            import gcsfs
            fs = gcsfs.GCSFileSystem()
            base = f"{storage._outputs_bucket}/{job_id}/output"
            matches = fs.glob(f"{base}/spatial_metrics_{model}_{window}.nc")
            if not matches:
                matches = fs.glob(f"{base}/spatial_metrics_{model}_{w_alt}.nc")
            matches = [f"gs://{f}" for f in matches]

        if not matches:
            raise HTTPException(status_code=404, detail=f"Grid file for {model}/{window} not found")

        if storage.is_local:
            ds = xr.open_dataset(matches[0])
        else:
            with fs.open(matches[0].removeprefix("gs://"), "rb") as f:
                ds = xr.load_dataset(f)
        if metric not in ds.data_vars:
            ds.close()
            raise HTTPException(status_code=404, detail=f"Metric {metric!r} not found in grid")

        da = ds[metric]
        if "lat" in da.dims and "lon" in da.dims:
            da = da.transpose("lat", "lon")
        da = da.squeeze()

        lats = [float(v) for v in da.lat.values]
        lons = [float(v) for v in da.lon.values]

        arr = da.values.astype(float)
        if arr.ndim != 2:
            ds.close()
            raise HTTPException(status_code=500, detail=f"Expected 2D array, got {arr.ndim}D {arr.shape}")

        values = np.where(np.isnan(arr), None, arr).tolist()

        UNIT_MAP = {"false_alarm_rate": "fraction", "miss_rate": "fraction"}
        unit = UNIT_MAP.get(metric, "days")
        valid = arr[~np.isnan(arr)]
        v_min = float(valid.min()) if len(valid) > 0 else 0.0
        v_max = float(valid.max()) if len(valid) > 0 else 0.0

        ds.close()
        return JobGridResponse(
            job_id=job_id, model=model, window=window, metric=metric,
            lats=lats, lons=lons, values=values, unit=unit, min=v_min, max=v_max,
        )

    return await asyncio.to_thread(_load)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: str, user: CurrentUser):
    def _delete():
        with get_db() as conn:
            row = conn.execute(
                text("SELECT id FROM jobs WHERE id = :id AND user_id = :uid"),
                {"id": job_id, "uid": user["id"]},
            ).fetchone()
            if not row:
                return False
            conn.execute(text("DELETE FROM jobs WHERE id = :id"), {"id": job_id})
            return True

    found = await asyncio.to_thread(_delete)
    if not found:
        raise HTTPException(status_code=404, detail="Job not found")

    # Best-effort cleanup of output files
    storage = get_storage()
    if storage.is_local:
        import shutil
        job_dir = storage._outputs_dir / job_id
        if job_dir.exists():
            await asyncio.to_thread(shutil.rmtree, job_dir)
    # GCS: let lifecycle rules handle expiry; no immediate deletion needed
