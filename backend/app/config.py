from pathlib import Path

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

_MODELS_YAML = Path(__file__).parent / "config" / "models.yaml"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # ---------------------------------------------------------------------------
    # Database
    # Local dev: SQLite. Production: Cloud SQL PostgreSQL via Auth Proxy socket.
    # DB_PASSWORD is injected separately from Secret Manager and merged into
    # the URL at engine creation time (see database.py).
    # ---------------------------------------------------------------------------
    database_url: str = "sqlite:///./almanac.db"
    db_password: str = ""

    # ---------------------------------------------------------------------------
    # Storage backend
    # "local" — filesystem under upload_dir / job_outputs_dir (dev default)
    # "gcs"   — Google Cloud Storage (production)
    # ---------------------------------------------------------------------------
    storage_backend: str = "local"
    upload_dir: str = "./uploads"
    job_outputs_dir: str = "./job_outputs"

    # GCS bucket names — required when storage_backend=gcs
    gcs_data_bucket: str = ""
    gcs_uploads_bucket: str = ""
    gcs_outputs_bucket: str = ""

    # ---------------------------------------------------------------------------
    # Job runner
    # "docker" — local Docker container (dev default)
    # "batch"  — Google Cloud Batch (production)
    # ---------------------------------------------------------------------------
    job_runner: str = "docker"
    romp_image: str = "romp:latest"
    romp_wrapper_image: str = ""  # if set, used instead of romp_image for Cloud Run jobs
    job_timeout_seconds: int = 3600
    job_cpu: str = "4"
    job_memory: str = "16Gi"
    # Probabilistic models load all ensemble members simultaneously and need
    # more resources. CPU and memory must be scaled together on Cloud Run.
    job_cpu_probabilistic: str = "8"
    job_memory_probabilistic: str = "32Gi"

    # Cloud Run / Batch settings — required when job_runner=cloudrun or batch
    gcp_project: str = ""
    gcp_region: str = "us-central1"
    batch_worker_sa: str = ""

    # Modal settings — required when job_runner=modal
    # MODAL_TOKEN_ID and MODAL_TOKEN_SECRET are read directly by the Modal client
    # from env; these fields just make them available for validation/logging.
    modal_token_id: str = ""
    modal_token_secret: str = ""

    # ---------------------------------------------------------------------------
    # Auth
    # ---------------------------------------------------------------------------
    frontend_url: str = "http://localhost:5173"
    cors_allow_all: bool = False
    globus_client_id: str = ""
    globus_client_secret: str = ""

    # ---------------------------------------------------------------------------
    # Demo datasets and model directories
    # In production these are GCS URIs (gs://almanac-data/obs/... etc.).
    # In local dev they are absolute paths on the developer's machine.
    # ---------------------------------------------------------------------------
    demo_obs_datasets: str = ""

    # India model directories
    india_aifs_model_dir: str = ""
    india_aifs_daily_model_dir: str = ""
    india_ifs_model_dir: str = ""
    india_neuralgcm_model_dir: str = ""
    india_fuxi_model_dir: str = ""
    india_graphcast_model_dir: str = ""
    india_gencast_model_dir: str = ""
    india_fuxi_s2s_model_dir: str = ""

    # Ethiopia model directories
    ethiopia_aifs_model_dir: str = ""
    ethiopia_fuxi_model_dir: str = ""
    ethiopia_graphcast_model_dir: str = ""
    ethiopia_gencast_model_dir: str = ""


settings = Settings()


# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

def get_model_registry() -> list[dict]:
    """Load model definitions from models.yaml and resolve model_dir from settings."""
    raw = yaml.safe_load(_MODELS_YAML.read_text())
    result = []
    for entry in raw:
        model_dir = getattr(settings, entry["model_dir_setting"], "")
        if not model_dir:
            continue
        m = {k: v for k, v in entry.items() if k != "model_dir_setting"}
        m["model_dir"] = model_dir
        result.append(m)
    return result


def get_demo_datasets() -> list[dict]:
    """
    Parse demo_obs_datasets setting into a list of dataset descriptors.
    Format: comma-separated "Name=path" or "Name=path|obs_file_pattern" pairs.
    Paths can be local filesystem paths (dev) or gs:// URIs (production).
    """
    result = []
    for entry in settings.demo_obs_datasets.split(","):
        entry = entry.strip()
        if not entry or "=" not in entry:
            continue
        name, _, rest = entry.partition("=")
        name = name.strip()
        if "|" in rest:
            path, _, obs_file_pattern = rest.partition("|")
            path = path.strip()
            obs_file_pattern = obs_file_pattern.strip() or None
        else:
            path = rest.strip()
            obs_file_pattern = None
        if name and path:
            demo_id = "demo:" + name.lower().replace(" ", "-").replace("(", "").replace(")", "").replace("°", "deg")
            result.append({
                "id": demo_id,
                "name": name,
                "obs_dir": path,
                "obs_file_pattern": obs_file_pattern,
            })
    return result
