from pydantic_settings import BaseSettings, SettingsConfigDict


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
    job_timeout_seconds: int = 3600

    # Cloud Batch settings — required when job_runner=batch
    gcp_project: str = ""
    gcp_region: str = "us-central1"
    batch_worker_sa: str = ""

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

    aifs_model_dir: str = ""
    aifs_daily_model_dir: str = ""
    ifs_model_dir: str = ""
    neuralgcm_model_dir: str = ""
    fuxi_model_dir: str = ""
    graphcast_model_dir: str = ""
    gencast_model_dir: str = ""
    fuxi_s2s_model_dir: str = ""


settings = Settings()


# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

def get_model_registry() -> list[dict]:
    candidates = [
        {
            "id": "aifs",
            "display_name": "AIFS",
            "model_type": "AIWP",
            "model_dir": settings.aifs_model_dir,
            "model_var": "tp",
            "unit_cvt": 1000,
            "file_pattern": "{}.nc",
            "probabilistic": False,
            "members": None,
            "init_days": "0,3",
            "date_filter_year": 2013,
            "start_date": "1964-05-01",
            "end_date": "2018-07-31",
            "start_year_clim": 1964,
            "end_year_clim": 2018,
        },
        {
            "id": "aifs_daily",
            "display_name": "AIFS (Daily)",
            "model_type": "AIWP",
            "model_dir": settings.aifs_daily_model_dir,
            "model_var": "tp",
            "unit_cvt": 1000,
            "file_pattern": "{}.nc",
            "probabilistic": False,
            "members": None,
            "init_days": "0,1,2,3,4,5,6",
            "start_date": "2019-05-01",
            "end_date": "2024-07-31",
            "start_year_clim": 1991,
            "end_year_clim": 2024,
        },
        {
            "id": "ifs",
            "display_name": "IFS-S2S",
            "model_type": "NWP",
            "model_dir": settings.ifs_model_dir,
            "model_var": "tp",
            "unit_cvt": 1000,
            "file_pattern": "{}.nc",
            "probabilistic": True,
            "members": None,
            "init_days": "0,3",
            "date_filter_year": 2013,
            "start_date": "2004-05-01",
            "end_date": "2023-07-31",
            "start_year_clim": 1991,
            "end_year_clim": 2023,
        },
        {
            "id": "neuralgcm",
            "display_name": "NeuralGCM",
            "model_type": "AIWP",
            "model_dir": settings.neuralgcm_model_dir,
            "model_var": "tp",
            "unit_cvt": 1000,
            "file_pattern": "{}.nc",
            "probabilistic": True,
            "members": None,
            "init_days": "0,3",
            "date_filter_year": 2013,
            "start_date": "1965-05-01",
            "end_date": "2024-07-31",
            "start_year_clim": 1965,
            "end_year_clim": 2024,
        },
        {
            "id": "fuxi",
            "display_name": "FuXi",
            "model_type": "AIWP",
            "model_dir": settings.fuxi_model_dir,
            "model_var": "tp",
            "unit_cvt": 1000,
            "file_pattern": "{}.nc",
            "probabilistic": False,
            "members": None,
            "init_days": "0,3",
            "date_filter_year": 2013,
            "start_date": "1964-05-01",
            "end_date": "2024-07-31",
            "start_year_clim": 1964,
            "end_year_clim": 2024,
        },
        {
            "id": "graphcast",
            "display_name": "GraphCast",
            "model_type": "AIWP",
            "model_dir": settings.graphcast_model_dir,
            "model_var": "tp",
            "unit_cvt": 1000,
            "file_pattern": "{}.nc",
            "probabilistic": False,
            "members": None,
            "init_days": "0,3",
            "date_filter_year": 2013,
            "start_date": "1965-05-01",
            "end_date": "2024-07-31",
            "start_year_clim": 1965,
            "end_year_clim": 2024,
        },
        {
            "id": "gencast",
            "display_name": "GenCast",
            "model_type": "AIWP",
            "model_dir": settings.gencast_model_dir,
            "model_var": "tp",
            "unit_cvt": 1000,
            "file_pattern": "{}.nc",
            "probabilistic": True,
            "members": None,
            "init_days": "0,3",
            "date_filter_year": 2019,
            "start_date": "2019-05-01",
            "end_date": "2024-07-31",
            "start_year_clim": 1991,
            "end_year_clim": 2024,
        },
        {
            "id": "fuxi_s2s",
            "display_name": "FuXi-S2S",
            "model_type": "AIWP",
            "model_dir": settings.fuxi_s2s_model_dir,
            "model_var": "tp",
            "unit_cvt": 1000,
            "file_pattern": "{}.nc",
            "probabilistic": True,
            "members": None,
            "init_days": "0,3",
            "date_filter_year": 2002,
            "start_date": "2002-05-01",
            "end_date": "2021-07-31",
            "start_year_clim": 1991,
            "end_year_clim": 2021,
        },
    ]
    return [m for m in candidates if m["model_dir"]]


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
