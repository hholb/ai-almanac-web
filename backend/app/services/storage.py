"""
Storage service — local filesystem vs GCS.

Selected via STORAGE_BACKEND env var:
  local  — files live on disk under upload_dir / job_outputs_dir (default for dev)
  gcs    — files live in GCS; upload/download URLs are signed GCS URLs

Both implementations share the same interface so routers don't need to care.
"""

from __future__ import annotations

import datetime
import os
import threading
from abc import ABC, abstractmethod
from pathlib import Path

# HDF5/NetCDF4 is not thread-safe. Serialize all dataset opens with this lock.
_nc_lock = threading.Lock()


class StorageBackend(ABC):
    @abstractmethod
    def generate_upload_url(
        self,
        storage_key: str,
        base_url: str,
    ) -> str:
        """Return a URL the client can PUT a file to."""

    @abstractmethod
    def confirm_upload(self, storage_key: str) -> bool:
        """Return True if the object exists (upload completed)."""

    @abstractmethod
    def resolve_obs_path(self, storage_key: str) -> str:
        """
        Resolve a dataset storage_key to a path the ROMP container can read.
        Local: absolute filesystem path.
        GCS: gs://bucket/key (Cloud Batch FUSE-mounts it).
        """

    @abstractmethod
    def job_output_uri(self, job_id: str) -> tuple[str, str]:
        """
        Return (output_uri, figure_uri) where ROMP should write results.
        Local: absolute paths. GCS: gs:// URIs.
        """

    @abstractmethod
    def generate_result_url(self, job_id: str, kind: str, filename: str) -> str:
        """Return a URL to serve a result file to the browser."""

    @abstractmethod
    def result_file_path(self, job_id: str, kind: str, filename: str) -> Path | None:
        """
        Return a local Path to stream via FileResponse, or None if the file
        should be served via redirect (GCS signed URL).
        """

    @abstractmethod
    def list_result_files(self, job_id: str) -> list[tuple[str, str]]:
        """Return [(kind, filename), ...] for all result files for a job."""

    @abstractmethod
    def list_nc_output_files(self, job_id: str) -> list:
        """Return list of spatial_metrics_*.nc paths/URIs for a job."""

    @abstractmethod
    def find_nc_output_file(self, job_id: str, model: str, window: str) -> str | None:
        """
        Return the path/URI for spatial_metrics_{model}_{window}.nc, or None if
        not found. Tries both the original window string and a hyphen→comma variant.
        """

    @abstractmethod
    def open_nc_dataset(self, path):
        """Open a NetCDF path/URI and return an xarray Dataset."""

    @property
    def is_local(self) -> bool:
        return isinstance(self, LocalStorage)


# ---------------------------------------------------------------------------
# Local implementation
# ---------------------------------------------------------------------------

class LocalStorage(StorageBackend):
    def __init__(self, upload_dir: str, job_outputs_dir: str):
        self._upload_dir = Path(upload_dir).resolve()
        self._outputs_dir = Path(job_outputs_dir).resolve()

    def generate_upload_url(self, storage_key: str, base_url: str) -> str:
        return base_url.rstrip("/") + f"/upload/{storage_key}"

    def confirm_upload(self, storage_key: str) -> bool:
        return (self._upload_dir / storage_key).exists()

    def resolve_obs_path(self, storage_key: str) -> str:
        key = Path(storage_key)
        if key.is_absolute():
            return str(key)
        return str((self._upload_dir / storage_key).parent)

    def job_output_uri(self, job_id: str) -> tuple[str, str]:
        output = self._outputs_dir / job_id / "output"
        figure = self._outputs_dir / job_id / "figure"
        output.mkdir(parents=True, exist_ok=True)
        figure.mkdir(parents=True, exist_ok=True)
        return str(output), str(figure)

    def generate_result_url(self, job_id: str, kind: str, filename: str) -> str:
        return f"/jobs/{job_id}/results/{kind}/{filename}"

    def result_file_path(self, job_id: str, kind: str, filename: str) -> Path | None:
        return self._outputs_dir / job_id / kind / filename

    def list_result_files(self, job_id: str) -> list[tuple[str, str]]:
        results = []
        job_dir = self._outputs_dir / job_id
        for kind in ("output", "figure"):
            d = job_dir / kind
            if d.exists():
                for f in sorted(d.iterdir()):
                    if f.is_file():
                        results.append((kind, f.name))
        return results

    def list_nc_output_files(self, job_id: str) -> list:
        output_dir = self._outputs_dir / job_id / "output"
        return sorted(output_dir.glob("spatial_metrics_*.nc")) if output_dir.exists() else []

    def find_nc_output_file(self, job_id: str, model: str, window: str) -> str | None:
        output_dir = self._outputs_dir / job_id / "output"
        for w in (window, window.replace("-", ",")):
            matches = list(output_dir.glob(f"spatial_metrics_{model}_{w}.nc"))
            if matches:
                return str(matches[0])
        return None

    def open_nc_dataset(self, path):
        import xarray as xr
        with _nc_lock:
            return xr.load_dataset(path)

    def log_path(self, job_id: str) -> Path:
        p = self._outputs_dir / job_id / "run.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def read_log(self, job_id: str) -> str:
        p = self._outputs_dir / job_id / "run.log"
        return p.read_text() if p.exists() else ""


# ---------------------------------------------------------------------------
# GCS implementation
# ---------------------------------------------------------------------------

class GCSStorage(StorageBackend):
    _SIGNED_URL_EXPIRY = datetime.timedelta(minutes=15)

    def __init__(self, uploads_bucket: str, outputs_bucket: str, data_bucket: str):
        from google.cloud import storage as gcs
        self._client = gcs.Client()
        self._uploads_bucket = uploads_bucket
        self._outputs_bucket = outputs_bucket
        self._data_bucket = data_bucket

    def _bucket(self, name: str):
        return self._client.bucket(name)

    def generate_upload_url(self, storage_key: str, base_url: str) -> str:
        blob = self._bucket(self._uploads_bucket).blob(storage_key)
        return blob.generate_signed_url(
            version="v4",
            expiration=self._SIGNED_URL_EXPIRY,
            method="PUT",
            content_type="application/octet-stream",
        )

    def confirm_upload(self, storage_key: str) -> bool:
        return self._bucket(self._uploads_bucket).blob(storage_key).exists()

    def resolve_obs_path(self, storage_key: str) -> str:
        # If already an absolute path (legacy from-path datasets), return as-is.
        if storage_key.startswith("gs://") or Path(storage_key).is_absolute():
            return storage_key
        # User upload: storage_key is "{user_id}/{dataset_id}/{filename}",
        # resolve to the parent prefix (the obs directory).
        prefix = "/".join(storage_key.split("/")[:-1])
        return f"gs://{self._uploads_bucket}/{prefix}"

    def job_output_uri(self, job_id: str) -> tuple[str, str]:
        return (
            f"gs://{self._outputs_bucket}/{job_id}/output",
            f"gs://{self._outputs_bucket}/{job_id}/figure",
        )

    def generate_result_url(self, job_id: str, kind: str, filename: str) -> str:
        blob = self._bucket(self._outputs_bucket).blob(f"{job_id}/{kind}/{filename}")
        return blob.generate_signed_url(
            version="v4",
            expiration=self._SIGNED_URL_EXPIRY,
            method="GET",
        )

    def result_file_path(self, job_id: str, kind: str, filename: str) -> Path | None:
        # GCS results are served via signed URL redirect, not local FileResponse.
        return None

    def list_result_files(self, job_id: str) -> list[tuple[str, str]]:
        results = []
        for kind in ("output", "figure"):
            prefix = f"{job_id}/{kind}/"
            blobs = self._client.list_blobs(self._outputs_bucket, prefix=prefix)
            for blob in sorted(blobs, key=lambda b: b.name):
                filename = blob.name.removeprefix(prefix)
                if filename:
                    results.append((kind, filename))
        return results

    def list_nc_output_files(self, job_id: str) -> list:
        import gcsfs
        fs = gcsfs.GCSFileSystem()
        prefix = f"{self._outputs_bucket}/{job_id}/output/spatial_metrics_"
        return [f"gs://{f}" for f in sorted(fs.glob(f"{prefix}*.nc"))]

    def find_nc_output_file(self, job_id: str, model: str, window: str) -> str | None:
        import gcsfs
        fs = gcsfs.GCSFileSystem()
        base = f"{self._outputs_bucket}/{job_id}/output"
        for w in (window, window.replace("-", ",")):
            matches = fs.glob(f"{base}/spatial_metrics_{model}_{w}.nc")
            if matches:
                return f"gs://{matches[0]}"
        return None

    def open_nc_dataset(self, path):
        import xarray as xr
        import gcsfs
        fs = gcsfs.GCSFileSystem()
        with fs.open(str(path).removeprefix("gs://"), "rb") as f:
            return xr.load_dataset(f, engine="h5netcdf")

    def read_log(self, job_id: str) -> str:
        blob = self._bucket(self._outputs_bucket).blob(f"{job_id}/run.log")
        return blob.download_as_text() if blob.exists() else ""


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_instance: StorageBackend | None = None


def get_storage() -> StorageBackend:
    global _instance
    if _instance is None:
        _instance = _make_storage()
    return _instance


def _make_storage() -> StorageBackend:
    from ..config import settings
    backend = settings.storage_backend.lower()
    if backend == "gcs":
        return GCSStorage(
            uploads_bucket=settings.gcs_uploads_bucket,
            outputs_bucket=settings.gcs_outputs_bucket,
            data_bucket=settings.gcs_data_bucket,
        )
    # Default: local
    return LocalStorage(
        upload_dir=settings.upload_dir,
        job_outputs_dir=settings.job_outputs_dir,
    )
