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


def _to_host_path(path: str) -> str:
    """
    Translate a container-internal path to a host path for Docker volume mounts.
    Uses the DOCKER_PATH_MAP setting when the backend itself runs in a container.
    No-op when the setting is empty (backend running directly on the host).
    """
    from ..config import settings
    for entry in settings.docker_path_map.split(","):
        entry = entry.strip()
        if "=" not in entry:
            continue
        container_prefix, host_prefix = entry.split("=", 1)
        if path.startswith(container_prefix):
            return host_prefix + path[len(container_prefix):]
    return path


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
            "-v", f"{_to_host_path(config['obs_dir'])}:/data/obs:ro",
            "-v", f"{_to_host_path(config['model_dir'])}:/data/model:ro",
            "-v", f"{_to_host_path(output_dir)}:/data/output",
            "-v", f"{_to_host_path(figure_dir)}:/data/figure",
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
# Cloud Run Jobs runner (production)
# ---------------------------------------------------------------------------

class CloudRunJobRunner(JobRunner):
    def __init__(
        self,
        romp_image: str,
        job_timeout_seconds: int,
        project: str,
        region: str,
        worker_sa: str,
        outputs_bucket: str,
        job_cpu: str = "4",
        job_memory: str = "16Gi",
        job_cpu_probabilistic: str = "8",
        job_memory_probabilistic: str = "32Gi",
    ):
        self._image = romp_image
        self._timeout = job_timeout_seconds
        self._project = project
        self._region = region
        self._worker_sa = worker_sa
        self._outputs_bucket = outputs_bucket
        self._job_cpu = job_cpu
        self._job_memory = job_memory
        self._job_cpu_prob = job_cpu_probabilistic
        self._job_memory_prob = job_memory_probabilistic

    def run_job(self, job_id: str, config: dict) -> None:
        t = threading.Thread(target=self._submit, args=(job_id, config), daemon=True)
        t.start()

    def _submit(self, job_id: str, config: dict) -> None:
        from google.cloud import run_v2
        from google.protobuf import duration_pb2

        romp_params = config.get("romp_params", {})
        probabilistic = str(romp_params.get("probabilistic", "false")).lower() == "true"
        cpu     = self._job_cpu_prob     if probabilistic else self._job_cpu
        memory  = self._job_memory_prob  if probabilistic else self._job_memory

        # Build GCS volumes and derive container-local paths from gs:// URIs.
        # One volume per unique bucket, mounted at /mnt/{bucket-name}.
        volumes: list[run_v2.Volume] = []
        volume_mounts: list[run_v2.VolumeMount] = []

        def _local_path(uri: str, read_only: bool) -> str:
            bucket, _, prefix = uri.removeprefix("gs://").partition("/")
            if not any(v.name == bucket for v in volumes):
                volumes.append(run_v2.Volume(
                    name=bucket,
                    gcs=run_v2.GCSVolumeSource(bucket=bucket, read_only=read_only),
                ))
                volume_mounts.append(run_v2.VolumeMount(
                    name=bucket, mount_path=f"/mnt/{bucket}",
                ))
            return f"/mnt/{bucket}/{prefix}".rstrip("/")

        obs_local   = _local_path(config["obs_dir"],   read_only=True)
        model_local = _local_path(config["model_dir"], read_only=True)
        _local_path(f"gs://{self._outputs_bucket}/",   read_only=False)

        env_vars = [
            run_v2.EnvVar(name="ROMP_OBS_DIR",    value=obs_local),
            run_v2.EnvVar(name="ROMP_MODEL_DIR",  value=model_local),
            run_v2.EnvVar(name="ROMP_MODEL_NAME", value=config["model_name"]),
            run_v2.EnvVar(name="ROMP_DIR_OUT",    value=f"/mnt/{self._outputs_bucket}/{job_id}/output"),
            run_v2.EnvVar(name="ROMP_DIR_FIG",    value=f"/mnt/{self._outputs_bucket}/{job_id}/figure"),
            *[run_v2.EnvVar(name=f"ROMP_{k.upper()}", value=str(v))
              for k, v in romp_params.items() if v is not None],
        ]

        job_name = f"romp-{job_id.replace('_', '-')}"[:49]
        parent   = f"projects/{self._project}/locations/{self._region}"

        cloud_run_job = run_v2.Job(
            template=run_v2.ExecutionTemplate(
                template=run_v2.TaskTemplate(
                    containers=[run_v2.Container(
                        image=self._image,
                        env=env_vars,
                        volume_mounts=volume_mounts,
                        resources=run_v2.ResourceRequirements(
                            limits={"cpu": cpu, "memory": memory},
                        ),
                    )],
                    volumes=volumes,
                    service_account=self._worker_sa,
                    max_retries=0,
                    timeout=duration_pb2.Duration(seconds=self._timeout),
                ),
            ),
        )

        jobs_client = run_v2.JobsClient()
        execution_name: str | None = None

        try:
            jobs_client.create_job(
                parent=parent, job=cloud_run_job, job_id=job_name,
            ).result(timeout=None)
            logger.info("Created Cloud Run Job %s for job_id %s", job_name, job_id)

            execution = jobs_client.run_job(
                name=f"{parent}/jobs/{job_name}",
            ).result(timeout=None)
            execution_name = execution.name
            logger.info("Started execution %s", execution_name)

            self._poll(job_id, execution_name)

        except Exception as exc:
            _update_status(job_id, "failed", error=str(exc))
            logger.exception("Cloud Run Job failed for %s", job_id)
        finally:
            try:
                jobs_client.delete_job(name=f"{parent}/jobs/{job_name}").result()
            except Exception:
                pass

    def _fetch_execution_error(self, execution_name: str) -> str:
        from .logging import fetch_cloud_logs
        execution_id = execution_name.split("/")[-1]
        filter_expr = (
            f'resource.type="cloud_run_job" '
            f'AND labels."run.googleapis.com/execution_name"=~"{execution_id}"'
        )
        result = fetch_cloud_logs(filter_expr, max_entries=20, descending=True)
        return result if result != "(no logs found)" else "Cloud Run Job task failed — check Cloud Logging"

    def _poll(self, job_id: str, execution_name: str) -> None:
        import time
        from google.cloud import run_v2

        client = run_v2.ExecutionsClient()
        while True:
            time.sleep(15)
            try:
                ex = client.get_execution(name=execution_name)
                if ex.succeeded_count > 0:
                    _update_status(job_id, "complete")
                    logger.info("Execution %s succeeded", execution_name)
                    return
                if ex.failed_count > 0:
                    error_msg = _fetch_execution_error(execution_name)
                    _update_status(job_id, "failed", error=error_msg)
                    logger.error("Execution %s failed", execution_name)
                    return
            except Exception as exc:
                logger.exception("Error polling execution %s: %s", execution_name, exc)


# ---------------------------------------------------------------------------
# Modal runner (production alternative to Cloud Run Jobs)
# ---------------------------------------------------------------------------

class ModalRunner(JobRunner):
    def __init__(self, outputs_bucket: str, job_timeout_seconds: int):
        self._outputs_bucket = outputs_bucket
        self._timeout = job_timeout_seconds

    def run_job(self, job_id: str, config: dict) -> None:
        t = threading.Thread(target=self._submit_and_poll, args=(job_id, config), daemon=True)
        t.start()

    def _submit_and_poll(self, job_id: str, config: dict) -> None:
        import time
        import modal

        try:
            run_romp = modal.Function.from_name("almanac-romp", "run_romp")
            handle = run_romp.spawn(job_id, config, self._outputs_bucket)
            logger.info("Spawned Modal function for job %s", job_id)
        except Exception as exc:
            _update_status(job_id, "failed", error=f"Failed to spawn Modal function: {exc}")
            logger.exception("Failed to spawn Modal job %s", job_id)
            return

        deadline = time.time() + self._timeout
        while time.time() < deadline:
            time.sleep(15)
            try:
                handle.get(timeout=0)
                _update_status(job_id, "complete")
                logger.info("Modal job %s completed", job_id)
                return
            except TimeoutError:
                continue  # still running
            except Exception as exc:
                _update_status(job_id, "failed", error=str(exc))
                logger.error("Modal job %s failed: %s", job_id, exc)
                return

        handle.cancel()
        _update_status(job_id, "failed", error="Job exceeded timeout")
        logger.error("Modal job %s timed out", job_id)


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
    if runner == "modal":
        return ModalRunner(
            outputs_bucket=settings.gcs_outputs_bucket,
            job_timeout_seconds=settings.job_timeout_seconds,
        )
    if runner in ("cloudrun", "batch"):
        image = settings.romp_wrapper_image or settings.romp_image
        return CloudRunJobRunner(
            romp_image=image,
            job_timeout_seconds=settings.job_timeout_seconds,
            project=settings.gcp_project,
            region=settings.gcp_region,
            worker_sa=settings.batch_worker_sa,
            outputs_bucket=settings.gcs_outputs_bucket,
            job_cpu=settings.job_cpu,
            job_memory=settings.job_memory,
            job_cpu_probabilistic=settings.job_cpu_probabilistic,
            job_memory_probabilistic=settings.job_memory_probabilistic,
        )
    # Default: docker
    return DockerRunner(
        romp_image=settings.romp_image,
        job_timeout_seconds=settings.job_timeout_seconds,
        storage=get_storage(),
    )
