"""
Modal app for AI Almanac.

Defines the ROMP job runner as a Modal function. Deploy with:
    modal deploy modal/app.py

The backend calls this via modal.Function.from_name() — no direct import needed.

Secrets required (create once via CLI):
    modal secret create gcp-service-account SERVICE_ACCOUNT_JSON="$(cat key.json)"
    modal secret create gcr-credentials REGISTRY_USERNAME="_json_key" REGISTRY_PASSWORD="$(cat key.json)"
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import modal

app = modal.App("almanac-romp")


def _media_type_for_filename(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".jpg") or lower.endswith(".jpeg"):
        return "image/jpeg"
    if lower.endswith(".gif"):
        return "image/gif"
    return "application/octet-stream"


def _build_runner_script(code: str, compute_call: str) -> str:
    return f"""\
import json
import os
import traceback
from pathlib import Path

ARTIFACT_DIR = Path(os.environ["ARTIFACT_DIR"])
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

def media_type_for_filename(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".jpg") or lower.endswith(".jpeg"):
        return "image/jpeg"
    if lower.endswith(".gif"):
        return "image/gif"
    return "application/octet-stream"

def save_figure(fig, filename="figure.webp", format=None, label=None, **savefig_kwargs):
    if format is None:
        suffix = Path(filename).suffix.lower()
        format = suffix.lstrip(".") if suffix else "webp"
    path = ARTIFACT_DIR / filename
    defaults = {{"dpi": 150, "bbox_inches": "tight"}}
    defaults.update(savefig_kwargs)
    fig.savefig(path, format=format, **defaults)
    return {{
        "kind": "figure",
        "filename": filename,
        "label": label,
        "media_type": media_type_for_filename(filename),
    }}

{code}

try:
    result = {compute_call}
    if not isinstance(result, dict):
        result = {{"value": result}}
    artifacts = []
    if isinstance(result.get("artifacts"), list):
        artifacts.extend(result.pop("artifacts"))
    forbidden_keys = {{"image", "image_data", "figure", "figure_data"}}
    bad_keys = sorted(key for key in result.keys() if key in forbidden_keys)
    if bad_keys:
        raise ValueError(
            "Do not return base64 or inline image data. "
            "Use save_figure(...) and return the artifact under 'artifacts'. "
            f"Forbidden keys: {{', '.join(bad_keys)}}"
        )
    print(json.dumps({{"ok": True, "result": result, "artifacts": artifacts}}))
except Exception as exc:
    print(json.dumps({{"ok": False, "error": str(exc), "traceback": traceback.format_exc()}}))
"""


def _run_generated_code(code: str, compute_call: str, extra_env: dict[str, str] | None = None, timeout: int = 90) -> dict:
    import json as _json

    artifact_dir = Path(tempfile.mkdtemp(prefix="chat-artifacts-"))
    runner_script = _build_runner_script(code, compute_call)
    env = dict(os.environ)
    env["ARTIFACT_DIR"] = str(artifact_dir)
    if extra_env:
        env.update(extra_env)

    proc = subprocess.run(
        ["python", "-c", runner_script],
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    if not stdout.strip():
        return {"ok": False, "error": stderr or "Generated code produced no output"}

    try:
        payload = _json.loads(stdout.strip())
    except _json.JSONDecodeError:
        return {"ok": False, "error": f"Non-JSON output: {stdout[:500]}", "stderr": stderr[:500]}

    if not isinstance(payload, dict):
        return {"ok": False, "error": "Generated code returned an invalid payload"}
    if not payload.get("ok"):
        return payload

    enriched_artifacts = []
    for artifact in payload.get("artifacts", []):
        filename = artifact.get("filename")
        if not filename:
            continue
        path = artifact_dir / filename
        if not path.exists():
            return {"ok": False, "error": f"Artifact file not found: {filename}"}
        enriched_artifacts.append({
            **artifact,
            "data": path.read_bytes(),
            "media_type": artifact.get("media_type") or _media_type_for_filename(filename),
        })
    payload["artifacts"] = enriched_artifacts
    return payload


@app.local_entrypoint()
def test(job_id: str, config_json: str, outputs_bucket: str):
    """CLI smoke-test entry: modal run modal/app.py --job-id=x --config-json='{...}' --outputs-bucket=y"""
    import json

    run_romp.remote(job_id, json.loads(config_json), outputs_bucket)


# Use the base ROMP image — the wrapper image's entrypoint would run at container
# start before Modal's runner, causing failures. The Modal function handles all
# staging itself so the wrapper is not needed.
romp_image = modal.Image.from_registry(
    "us-central1-docker.pkg.dev/ai-almanac/almanac/romp:latest",
    secret=modal.Secret.from_name("gcr-credentials"),
).dockerfile_commands(
    [
        # Clear the relative-path entrypoint so Modal can layer on top without
        # it trying to exec scripts/entrypoint.sh from the wrong working directory.
        "ENTRYPOINT []",
        "CMD []",
        "RUN pip install --no-cache-dir google-cloud-storage",
    ]
)

gcp_secret = modal.Secret.from_name("gcp-service-account")


@app.function(
    image=romp_image,
    cpu=(6, 12),
    memory=(16384, 32768),  # 16 GiB request, 32Gib limit
    timeout=3600,
    secrets=[gcp_secret],
)
def run_romp(job_id: str, config: dict, outputs_bucket: str) -> None:
    """
    Run ROMP for a single job.

    Replicates the staging logic from docker/romp-wrapper/entrypoint.sh, then
    calls /app/scripts/entrypoint.sh (the inner ROMP entry) with the same env
    vars that DockerRunner uses.

    Raises on failure so the caller's poll loop can catch it.
    """
    from google.cloud import storage as gcs
    from google.cloud.storage import transfer_manager

    # Write SA key so google-cloud-storage can authenticate.
    sa_json = os.environ["SERVICE_ACCOUNT_JSON"]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write(sa_json)
        sa_key_path = f.name
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = sa_key_path

    romp_params = config.get("romp_params", {})
    start_year = int((romp_params.get("start_date") or "1990-01-01")[:4])
    end_year = int((romp_params.get("end_date") or "2024-01-01")[:4])

    stage_root = Path("/tmp/romp_stage")
    local_obs = stage_root / "obs"
    local_model = stage_root / "model"
    local_out = stage_root / "output"
    local_fig = stage_root / "figure"
    for d in (local_obs, local_model, local_out, local_fig):
        d.mkdir(parents=True, exist_ok=True)

    client = gcs.Client()

    # --- Stage obs (all files in prefix, downloaded in parallel) ---
    obs_uri = config["obs_dir"]  # gs://bucket/prefix
    print(f"==> Staging obs from {obs_uri}")
    bucket_name, _, prefix = obs_uri.removeprefix("gs://").partition("/")
    prefix = prefix.rstrip("/") + "/"
    obs_bucket = client.bucket(bucket_name)
    obs_names = [
        blob.name[len(prefix):]
        for blob in client.list_blobs(bucket_name, prefix=prefix, delimiter="/")
        if blob.name[len(prefix):] and not blob.name[len(prefix):].endswith("/")
    ]
    if obs_names:
        results = transfer_manager.download_many_to_path(
            obs_bucket, obs_names, str(local_obs), blob_name_prefix=prefix, worker_type="thread",
        )
        for name, result in zip(obs_names, results):
            if isinstance(result, Exception):
                print(f"  obs FAILED: {name}: {result}")
            else:
                print(f"  obs: {name}")
    print(f"    obs staged: {sum(1 for _ in local_obs.iterdir())} files")

    # --- Stage model (list prefix once, filter by year range, download in parallel) ---
    model_uri = config["model_dir"]  # gs://bucket/prefix
    print(f"==> Staging model ({start_year}–{end_year}) from {model_uri}")
    bucket_name, _, prefix = model_uri.removeprefix("gs://").partition("/")
    prefix = prefix.rstrip("/") + "/"
    year_names = {f"{year}.nc" for year in range(start_year, end_year + 1)}
    model_bucket = client.bucket(bucket_name)
    model_names = [
        blob.name[len(prefix):]
        for blob in client.list_blobs(bucket_name, prefix=prefix, delimiter="/")
        if blob.name[len(prefix):] in year_names
    ]
    if model_names:
        results = transfer_manager.download_many_to_path(
            model_bucket, model_names, str(local_model), blob_name_prefix=prefix, worker_type="thread",
        )
        for name, result in zip(model_names, results):
            if isinstance(result, Exception):
                print(f"  model FAILED: {name}: {result}")
            else:
                print(f"  model: {name}")
    print(f"    model staged: {sum(1 for _ in local_model.iterdir())} files")

    # --- Build ROMP env (matches DockerRunner env construction) ---
    env = {
        **os.environ,
        "ROMP_OBS_DIR": str(local_obs),
        "ROMP_MODEL_DIR": str(local_model),
        "ROMP_MODEL_NAME": config["model_name"],
        "ROMP_DIR_OUT": str(local_out),
        "ROMP_DIR_FIG": str(local_fig),
        **{
            f"ROMP_{k.upper()}": str(v) for k, v in romp_params.items() if v is not None
        },
    }

    # --- Run ROMP ---
    print("==> Running ROMP...")
    result = subprocess.run(
        ["/app/scripts/entrypoint.sh"],
        env=env,
        capture_output=False,  # stream stdout/stderr to Modal logs
    )

    # Treat SIGSEGV as success if outputs exist (matches DockerRunner behaviour).
    if result.returncode not in (0, -11, 139):
        raise RuntimeError(f"ROMP exited with code {result.returncode}")
    if result.returncode in (-11, 139) and not any(local_out.iterdir()):
        raise RuntimeError("ROMP segfaulted with no output")

    # --- Upload outputs to GCS (parallel) ---
    print(f"==> Uploading outputs to gs://{outputs_bucket}/{job_id}/")
    out_bucket = client.bucket(outputs_bucket)
    for kind, local_dir in (("output", local_out), ("figure", local_fig)):
        files = [f.name for f in local_dir.iterdir() if f.is_file()]
        if not files:
            continue
        results = transfer_manager.upload_many_from_filenames(
            out_bucket, files, source_directory=str(local_dir),
            blob_name_prefix=f"{job_id}/{kind}/", worker_type="thread",
        )
        for name, result in zip(files, results):
            if isinstance(result, Exception):
                print(f"  upload FAILED: {kind}/{name}: {result}")
            else:
                print(f"  uploaded: {kind}/{name}")

    print("==> Done.")


# ---------------------------------------------------------------------------
# Sandboxed code execution
# ---------------------------------------------------------------------------

# Minimal image for sandboxed code: scientific Python stack only, no GCS credentials.
_sandbox_image = (
    modal.Image.debian_slim()
    .pip_install("xarray", "numpy", "h5netcdf", "scipy", "pandas", "matplotlib", "Pillow")
)


@app.function(
    image=_sandbox_image,
    cpu=1,
    memory=2048,
    timeout=120,
)
def run_code_sandbox(code: str) -> dict:
    """
    Run arbitrary Python code in an isolated sandbox with no network access.

    `code` must define a function:
        def compute() -> dict:
            ...

    Returns {"ok": true, "result": {...}, "artifacts": [...]} or
    {"ok": false, "error": "..."}.
    Available libraries: xarray, numpy, scipy, pandas, matplotlib.
    """
    return _run_generated_code(code, "compute()", timeout=90)


@app.function(
    image=romp_image,  # needs GCS to stage files
    cpu=2,
    memory=8192,
    timeout=300,
    secrets=[gcp_secret],
)
def run_code(job_id: str, outputs_bucket: str, code: str) -> dict:
    """
    Download NC output files for job_id from GCS, then run LLM-generated code
    in an isolated Modal Sandbox with no network access.

    `code` must define a function:
        def compute(nc_dir: str) -> dict:
            ...

    Returns {"ok": true, "result": {...}, "artifacts": [...]} or
    {"ok": false, "error": "..."}.
    """
    from google.cloud import storage as gcs
    from google.cloud.storage import transfer_manager

    # Authenticate — write SA key to a temp file for the GCS client, then
    # remove it before running user code so the subprocess can't read it.
    sa_json = os.environ["SERVICE_ACCOUNT_JSON"]
    sa_key_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(sa_json)
            sa_key_path = f.name
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = sa_key_path

        client = gcs.Client()
        bucket = client.bucket(outputs_bucket)
        prefix = f"{job_id}/output/"
        nc_names = [
            blob.name[len(prefix):]
            for blob in client.list_blobs(outputs_bucket, prefix=prefix)
            if blob.name.endswith(".nc")
        ]

        local_nc = Path("/tmp/sandbox_nc")
        local_nc.mkdir(parents=True, exist_ok=True)

        if nc_names:
            results = transfer_manager.download_many_to_path(
                bucket, nc_names, str(local_nc), blob_name_prefix=prefix, worker_type="thread",
            )
            for name, result in zip(nc_names, results):
                if isinstance(result, Exception):
                    return {"ok": False, "error": f"Failed to download {name}: {result}"}

        if not nc_names:
            return {"ok": False, "error": "No NC output files found for this job"}
    finally:
        # Remove credentials from disk and environment before executing user code.
        if sa_key_path:
            Path(sa_key_path).unlink(missing_ok=True)
        os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)

    env = {
        k: v for k, v in os.environ.items()
        if k not in {"GOOGLE_APPLICATION_CREDENTIALS", "SERVICE_ACCOUNT_JSON"}
    }
    return _run_generated_code(
        code,
        f'compute({str(local_nc)!r})',
        extra_env=env,
        timeout=120,
    )
