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

    # --- Stage obs (all files in prefix, same logic as entrypoint.sh) ---
    obs_uri = config["obs_dir"]  # gs://bucket/prefix
    print(f"==> Staging obs from {obs_uri}")
    bucket_name, _, prefix = obs_uri.removeprefix("gs://").partition("/")
    prefix = prefix.rstrip("/") + "/"
    for blob in client.list_blobs(bucket_name, prefix=prefix, delimiter="/"):
        name = blob.name[len(prefix) :]
        if not name or name.endswith("/"):
            continue
        blob.download_to_filename(str(local_obs / name))
        print(f"  obs: {name}")
    print(f"    obs staged: {sum(1 for _ in local_obs.iterdir())} files")

    # --- Stage model (year-by-year, same logic as entrypoint.sh) ---
    model_uri = config["model_dir"]  # gs://bucket/prefix
    print(f"==> Staging model ({start_year}–{end_year}) from {model_uri}")
    bucket_name, _, prefix = model_uri.removeprefix("gs://").partition("/")
    prefix = prefix.rstrip("/") + "/"
    model_bucket = client.bucket(bucket_name)
    for year in range(start_year, end_year + 1):
        blob = model_bucket.blob(f"{prefix}{year}.nc")
        dest = local_model / f"{year}.nc"
        try:
            blob.download_to_filename(str(dest))
            print(f"  model: {year}.nc")
        except Exception:
            pass  # year not present
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

    # --- Upload outputs to GCS ---
    print(f"==> Uploading outputs to gs://{outputs_bucket}/{job_id}/")
    out_bucket = client.bucket(outputs_bucket)
    for kind, local_dir in (("output", local_out), ("figure", local_fig)):
        for f in local_dir.iterdir():
            if f.is_file():
                out_bucket.blob(f"{job_id}/{kind}/{f.name}").upload_from_filename(
                    str(f)
                )
                print(f"  uploaded: {kind}/{f.name}")

    print("==> Done.")
