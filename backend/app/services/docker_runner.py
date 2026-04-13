"""
Runs a ROMP job in a local Docker container.

In production this is replaced by Cloud Batch job submission, but the
interface stays the same: `run_job(job_id, config)` fires and forgets,
updating the DB row when the container exits.
"""

import logging
import subprocess
import threading
from pathlib import Path

from ..config import settings
from ..database import get_db

logger = logging.getLogger(__name__)


def _docker_cmd(job_id: str, config: dict) -> list[str]:
    output_dir = Path(settings.job_outputs_dir).resolve() / job_id / "output"
    figure_dir = Path(settings.job_outputs_dir).resolve() / job_id / "figure"
    log_path   = Path(settings.job_outputs_dir).resolve() / job_id / "run.log"

    output_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    romp_params = dict(config.get("romp_params", {}))

    # If nc_mask is a host path, mount its parent dir and rewrite to container path.
    extra_mounts = []
    nc_mask_host = romp_params.get("nc_mask")
    if nc_mask_host:
        mask_host_path = Path(nc_mask_host).resolve()
        extra_mounts += ["-v", f"{mask_host_path.parent}:/data/masks:ro"]
        romp_params["nc_mask"] = f"/data/masks/{mask_host_path.name}"

    ref_model_dir_host = romp_params.get("ref_model_dir")
    if ref_model_dir_host:
        rmd = Path(ref_model_dir_host).resolve()
        extra_mounts += ["-v", f"{rmd}:/data/ref_model:ro"]
        romp_params["ref_model_dir"] = "/data/ref_model"

    thresh_file_host = romp_params.get("thresh_file")
    if thresh_file_host:
        tf = Path(thresh_file_host).resolve()
        extra_mounts += ["-v", f"{tf.parent}:/data/thresh:ro"]
        romp_params["thresh_file"] = f"/data/thresh/{tf.name}"

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
    cmd.append(settings.romp_image)

    return cmd, log_path


def _run(job_id: str, config: dict) -> None:
    cmd, log_path = _docker_cmd(job_id, config)
    logger.info("Starting ROMP container for job %s", job_id)

    try:
        with log_path.open("w") as log_f:
            result = subprocess.run(
                cmd,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                timeout=settings.job_timeout_seconds,
            )

        if result.returncode == 0:
            _update_status(job_id, "complete")
            logger.info("Job %s completed", job_id)
        elif result.returncode == -11 or result.returncode == 139:
            # SIGSEGV in a C extension (e.g. rasterio) after outputs are written.
            # Treat as complete if output files exist, otherwise fail normally.
            output_dir = Path(settings.job_outputs_dir).resolve() / job_id / "output"
            has_output = output_dir.exists() and any(output_dir.iterdir())
            if has_output:
                _update_status(job_id, "complete")
                logger.warning("Job %s exited with segfault but has output — marking complete", job_id)
            else:
                _update_status(job_id, "failed", error="Container segfaulted with no output")
                logger.error("Job %s segfaulted with no output", job_id)
        else:
            _update_status(job_id, "failed", error=f"Container exited with code {result.returncode}")
            logger.error("Job %s failed (exit %d)", job_id, result.returncode)

    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "stop", f"romp-{job_id}"], check=False)
        _update_status(job_id, "failed", error="Job exceeded timeout")
        logger.error("Job %s timed out", job_id)
    except Exception as exc:
        _update_status(job_id, "failed", error=str(exc))
        logger.exception("Job %s raised an unexpected error", job_id)


def _update_status(job_id: str, status: str, error: str | None = None) -> None:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        if status == "complete":
            conn.execute(
                "UPDATE jobs SET status = ?, completed_at = ? WHERE id = ?",
                (status, now, job_id),
            )
        else:
            conn.execute(
                "UPDATE jobs SET status = ?, completed_at = ?, error = ? WHERE id = ?",
                (status, now, error, job_id),
            )


def run_job(job_id: str, config: dict) -> None:
    """Fire and forget — starts the container in a background thread."""
    t = threading.Thread(target=_run, args=(job_id, config), daemon=True)
    t.start()
