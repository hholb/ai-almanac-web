"""Spatial metrics aggregation from ROMP output NetCDF files.

All functions here are synchronous and intended to be called via
asyncio.to_thread() from the async route handlers in routers/jobs.py.
"""
from __future__ import annotations

from fastapi import HTTPException
from pydantic import BaseModel

from .storage import StorageBackend

# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

UNIT_MAP: dict[str, str] = {
    "false_alarm_rate": "fraction",
    "miss_rate": "fraction",
}


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
# Internal helpers
# ---------------------------------------------------------------------------

def _get_nc_files(storage: StorageBackend, job_id: str) -> list:
    if storage.is_local:
        output_dir = storage._outputs_dir / job_id / "output"
        return sorted(output_dir.glob("spatial_metrics_*.nc")) if output_dir.exists() else []
    import gcsfs
    fs = gcsfs.GCSFileSystem()
    prefix = f"{storage._outputs_bucket}/{job_id}/output/spatial_metrics_"
    return [f"gs://{f}" for f in sorted(fs.glob(f"{prefix}*.nc"))]


def _open_nc(storage: StorageBackend, path):
    import xarray as xr
    if storage.is_local:
        return xr.open_dataset(path)
    import gcsfs
    fs = gcsfs.GCSFileSystem()
    with fs.open(str(path).removeprefix("gs://"), "rb") as f:
        return xr.load_dataset(f, engine="h5netcdf")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_job_metrics(
    job_id: str,
    storage: StorageBackend,
    lat_min: float | None = None,
    lat_max: float | None = None,
    lon_min: float | None = None,
    lon_max: float | None = None,
) -> JobMetrics:
    """Aggregate spatial_metrics_*.nc files into domain-wide distribution stats."""
    try:
        import numpy as np
    except ImportError:
        raise HTTPException(status_code=503, detail="xarray not available on this server")

    nc_files = _get_nc_files(storage, job_id)
    has_bbox = any(v is not None for v in (lat_min, lat_max, lon_min, lon_max))

    windows: list[WindowMetrics] = []
    grid_info: GridInfo | None = None
    actual_bbox: dict | None = None

    for nc_file in nc_files:
        ds = _open_nc(storage, nc_file)

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
            metrics[var_str] = MetricStats(
                mean=float(np.mean(valid)),
                min=float(np.min(valid)),
                max=float(np.max(valid)),
                p25=float(np.percentile(valid, 25)),
                p50=float(np.percentile(valid, 50)),
                p75=float(np.percentile(valid, 75)),
                p90=float(np.percentile(valid, 90)),
                unit=UNIT_MAP.get(var_str, "days"),
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


def compute_job_grid(
    job_id: str,
    storage: StorageBackend,
    model: str,
    window: str,
    metric: str,
) -> JobGridResponse:
    """Load a single spatial_metrics_*.nc file and return the raw 2D grid."""
    try:
        import numpy as np
    except ImportError:
        raise HTTPException(status_code=503, detail="xarray not available")

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

    ds = _open_nc(storage, matches[0])
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
    unit = UNIT_MAP.get(metric, "days")
    valid = arr[~np.isnan(arr)]
    v_min = float(valid.min()) if len(valid) > 0 else 0.0
    v_max = float(valid.max()) if len(valid) > 0 else 0.0

    ds.close()
    return JobGridResponse(
        job_id=job_id, model=model, window=window, metric=metric,
        lats=lats, lons=lons, values=values, unit=unit, min=v_min, max=v_max,
    )
