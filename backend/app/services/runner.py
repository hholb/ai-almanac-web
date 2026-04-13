"""
Job runner — local Docker vs Cloud Batch.

Selected via JOB_RUNNER env var:
  docker  — runs ROMP in a local Docker container (default for dev)
  batch   — submits a Cloud Batch job (production)

Both call run_job(job_id, config) and return immediately; status updates
happen asynchronously as the job completes.
"""

from __future__ import annotations

import logging
import subprocess
import threading
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)


class JobRunner(ABC):
    @abstractmethod
    def run_job(self, job_id: str, config: dict) -> None:
        """Fire and forget — start the job, return immediately."""


# ---------------------------------------------------------------------------
# Docker runner (local dev)
# ---------------------------------------------------------------------------

class DockerRunner(JobRunner):
    def __init__(self, romp_image: str, job_timeout_seconds: int, storage):
        self._image = romp_image
        self._timeout = job_timeout_seconds
        self._storage = storage

    def run_job(self, job_id: str, config: dict) -> None:
        t = threading.Thread(target=self._run, args=(job_id, config), daemon=True)
        t.start()

    def _run(self, job_id: str, config: dict) -> None:
        from .storage import LocalStorage
        assert isinstance(self._storage, LocalStorage), \
            "DockerRunner requires LocalStorage"

        output_dir, figure_dir = self._storage.job_output_uri(job_id)
        log_path = self._storage.log_path(job_id)

        romp_params = dict(config.get("romp_params", {}))
        extra_mounts = []

        nc_mask_host = romp_params.get("nc_mask")
        if nc_mask_host:
            p = Path(nc_mask_host).resolve()
            extra_mounts += ["-v", f"{p.parent}:/data/masks:ro"]
            romp_params["nc_mask"] = f"/data/masks/{p.name}"

        ref_model_dir_host = romp_params.get("ref_model_dir")
        if ref_model_dir_host:
            p = Path(ref_model_dir_host).resolve()
            extra_mounts += ["-v", f"{p}:/data/ref_model:ro"]
            romp_params["ref_model_dir"] = "/data/ref_model"

        thresh_file_host = romp_params.get("thresh_file")
        if thresh_file_host:
            p = Path(thresh_file_host).resolve()
            extra_mounts += ["-v", f"{p.parent}:/data/thresh:ro"]
            romp_params["thresh_file"] = f"/data/thresh/{p.name}"

        env = {
            "ROMP_OBS_DIR":    "/data/obs",
            "ROMP_MODEL_DIR":  "/data/model",
            "ROMP_MODEL_NAME": config["model_name"],
            "ROMP_DIR_OUT":    "/data/output",
            "ROMP_DIR_FIG":    "/data/figure",
            **{f"ROMP_{k.upper()}": str(v) for k, v in romp_params.items() if v is not None},
        }

        cmd = [
            "docker", "run", "--rm",
            "--name", f"romp-{job_id}",
            "-v", f"{config['obs_dir']}:/data/obs:ro",
            "-v", f"{config['model_dir']}:/data/model:ro",
            "-v", f"{output_dir}:/data/output",
            "-v", f"{figure_dir}:/data/figure",
            *extra_mounts,
        ]
        for k, v in env.items():
            cmd += ["-e", f"{k}={v}"]
        cmd.append(self._image)

        logger.info("Starting ROMP container for job %s", job_id)
        try:
            with log_path.open("w") as log_f:
                result = subprocess.run(
                    cmd,
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                    timeout=self._timeout,
                )

            if result.returncode == 0:
                _update_status(job_id, "complete")
                logger.info("Job %s completed", job_id)
            elif result.returncode in (-11, 139):
                # SIGSEGV in a C extension after outputs are written — treat as success.
                if any(Path(output_dir).iterdir()):
                    _update_status(job_id, "complete")
                    logger.warning("Job %s segfaulted but has output — marking complete", job_id)
                else:
                    _update_status(job_id, "failed", error="Container segfaulted with no output")
            else:
                _update_status(job_id, "failed", error=f"Container exited with code {result.returncode}")

        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "stop", f"romp-{job_id}"], check=False)
            _update_status(job_id, "failed", error="Job exceeded timeout")
            logger.error("Job %s timed out", job_id)
        except Exception as exc:
            _update_status(job_id, "failed", error=str(exc))
            logger.exception("Job %s raised an unexpected error", job_id)


# ---------------------------------------------------------------------------
# Cloud Batch runner (production)
# ---------------------------------------------------------------------------

class BatchRunner(JobRunner):
    def __init__(
        self,
        romp_image: str,
        job_timeout_seconds: int,
        project: str,
        region: str,
        worker_sa: str,
        outputs_bucket: str,
    ):
        self._image = romp_image
        self._timeout = job_timeout_seconds
        self._project = project
        self._region = region
        self._worker_sa = worker_sa
        self._outputs_bucket = outputs_bucket

    def run_job(self, job_id: str, config: dict) -> None:
        t = threading.Thread(target=self._submit, args=(job_id, config), daemon=True)
        t.start()

    def _submit(self, job_id: str, config: dict) -> None:
        from google.cloud import batch_v1
        from google.protobuf import duration_pb2

        client = batch_v1.BatchServiceClient()

        romp_params = config.get("romp_params", {})
        env_vars = {
            "ROMP_OBS_DIR":    "/mnt/obs",
            "ROMP_MODEL_DIR":  "/mnt/model",
            "ROMP_MODEL_NAME": config["model_name"],
            "ROMP_DIR_OUT":    "/mnt/output",
            "ROMP_DIR_FIG":    "/mnt/figure",
            **{f"ROMP_{k.upper()}": str(v) for k, v in romp_params.items() if v is not None},
        }

        # Parse GCS URIs: gs://bucket/prefix -> (bucket, prefix)
        def _parse_gcs(uri: str) -> tuple[str, str]:
            parts = uri.removeprefix("gs://").split("/", 1)
            return parts[0], (parts[1] if len(parts) > 1 else "")

        obs_bucket, obs_prefix   = _parse_gcs(config["obs_dir"])
        model_bucket, model_prefix = _parse_gcs(config["model_dir"])
        out_prefix  = f"{job_id}/output"
        fig_prefix  = f"{job_id}/figure"

        def _gcs_volume(bucket: str, prefix: str, mount_path: str, readonly: bool):
            v = batch_v1.Volume()
            v.gcs = batch_v1.GCS(remote_path=f"{bucket}/{prefix}".rstrip("/"))
            v.mount_path = mount_path
            v.mount_options = ["implicit-dirs"] + (["ro"] if readonly else [])
            return v

        volumes = [
            _gcs_volume(obs_bucket,            obs_prefix,   "/mnt/obs",    readonly=True),
            _gcs_volume(model_bucket,          model_prefix, "/mnt/model",  readonly=True),
            _gcs_volume(self._outputs_bucket,  out_prefix,   "/mnt/output", readonly=False),
            _gcs_volume(self._outputs_bucket,  fig_prefix,   "/mnt/figure", readonly=False),
        ]

        runnable = batch_v1.Runnable(
            container=batch_v1.Runnable.Container(
                image_uri=self._image,
                entrypoint="",
            ),
            environment=batch_v1.Environment(variables=env_vars),
        )

        task_spec = batch_v1.TaskSpec(
            runnables=[runnable],
            volumes=volumes,
            max_retry_count=0,
            max_run_duration=duration_pb2.Duration(seconds=self._timeout),
        )

        job = batch_v1.Job(
            task_groups=[batch_v1.TaskGroup(
                task_spec=task_spec,
                task_count=1,
            )],
            allocation_policy=batch_v1.AllocationPolicy(
                instances=[batch_v1.AllocationPolicy.InstancePolicyOrTemplate(
                    policy=batch_v1.AllocationPolicy.InstancePolicy(
                        machine_type="n2-standard-4",
                        provisioning_model=batch_v1.AllocationPolicy.ProvisioningModel.SPOT,
                    ),
                )],
                service_account=batch_v1.ServiceAccount(email=self._worker_sa),
            ),
            logs_policy=batch_v1.LogsPolicy(
                destination=batch_v1.LogsPolicy.Destination.CLOUD_LOGGING,
            ),
        )

        parent = f"projects/{self._project}/locations/{self._region}"
        # Cloud Batch job IDs must be lowercase alphanumeric + hyphens, max 63 chars.
        batch_job_id = f"romp-{job_id.replace('_', '-')}"[:63]

        try:
            client.create_job(parent=parent, job=job, job_id=batch_job_id)
            logger.info("Submitted Cloud Batch job %s for job_id %s", batch_job_id, job_id)
            # Poll for completion in a background thread.
            self._poll(job_id, parent, batch_job_id, client)
        except Exception as exc:
            _update_status(job_id, "failed", error=str(exc))
            logger.exception("Failed to submit Batch job for %s", job_id)

    def _poll(
        self,
        job_id: str,
        parent: str,
        batch_job_id: str,
        client,
    ) -> None:
        import time
        from google.cloud import batch_v1

        job_name = f"{parent}/jobs/{batch_job_id}"
        while True:
            time.sleep(30)
            try:
                batch_job = client.get_job(name=job_name)
                state = batch_job.status.state
                if state == batch_v1.JobStatus.State.SUCCEEDED:
                    _update_status(job_id, "complete")
                    logger.info("Batch job %s succeeded", batch_job_id)
                    return
                if state in (
                    batch_v1.JobStatus.State.FAILED,
                    batch_v1.JobStatus.State.DELETION_IN_PROGRESS,
                ):
                    msg = f"Batch job state: {state.name}"
                    _update_status(job_id, "failed", error=msg)
                    logger.error("Batch job %s failed: %s", batch_job_id, msg)
                    return
                # QUEUED / SCHEDULED / RUNNING — keep polling
            except Exception as exc:
                logger.exception("Error polling Batch job %s: %s", batch_job_id, exc)


# ---------------------------------------------------------------------------
# Shared status helper
# ---------------------------------------------------------------------------

def _update_status(job_id: str, status: str, error: str | None = None) -> None:
    from datetime import datetime, timezone
    from ..database import get_db
    from sqlalchemy import text

    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        if status == "complete":
            conn.execute(
                text("UPDATE jobs SET status = :status, completed_at = :now WHERE id = :id"),
                {"status": status, "now": now, "id": job_id},
            )
        else:
            conn.execute(
                text("UPDATE jobs SET status = :status, completed_at = :now, error = :error WHERE id = :id"),
                {"status": status, "now": now, "error": error, "id": job_id},
            )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_instance: JobRunner | None = None


def get_runner() -> JobRunner:
    global _instance
    if _instance is None:
        _instance = _make_runner()
    return _instance


def _make_runner() -> JobRunner:
    from ..config import settings
    from .storage import get_storage

    runner = settings.job_runner.lower()
    if runner == "batch":
        return BatchRunner(
            romp_image=settings.romp_image,
            job_timeout_seconds=settings.job_timeout_seconds,
            project=settings.gcp_project,
            region=settings.gcp_region,
            worker_sa=settings.batch_worker_sa,
            outputs_bucket=settings.gcs_outputs_bucket,
        )
    # Default: docker
    return DockerRunner(
        romp_image=settings.romp_image,
        job_timeout_seconds=settings.job_timeout_seconds,
        storage=get_storage(),
    )
