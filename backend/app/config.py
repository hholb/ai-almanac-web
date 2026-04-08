from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    db_path: str = "./almanac.db"
    upload_dir: str = "./uploads"
    job_outputs_dir: str = "./job_outputs"
    frontend_url: str = "http://localhost:5173"
    cors_allow_all: bool = False

    romp_image: str = "romp:latest"
    job_timeout_seconds: int = 3600

    # Globus confidential client credentials — same client ID used by the frontend.
    # Leave empty to run in stub mode (token value used as user ID).
    globus_client_id: str = ""
    globus_client_secret: str = ""
    gcs_bucket_data: str = ""

    # Demo observation datasets — shown to all users for testing.
    # Add entries here for each pre-loaded obs directory on the server.
    # Format: comma-separated "Name=path" pairs.
    # e.g. demo_obs_datasets: str = "India Demo=/data/obs/india,Ethiopia Demo=/data/obs/ethiopia"
    demo_obs_datasets: str = "India Demo (2013–2020)=/Users/hayden/code/ROMP/demo/data/obs,Ethiopia (CHIRPS/IMERG 1998–2024)=/Users/hayden/code/ROMP/data/ethiopia/obs"

    # Model data directories — override per deployment via env vars.
    aifs_model_dir: str = "/Users/hayden/code/ROMP/data/india/aifs"
    aifs_daily_model_dir: str = "/Users/hayden/code/ROMP/data/india/aifs_daily"
    ifs_model_dir: str = "/Users/hayden/code/ROMP/data/india/ifs"
    neuralgcm_model_dir: str = "/Users/hayden/code/ROMP/data/india/neuralgcm"
    fuxi_model_dir: str = "/Users/hayden/code/ROMP/data/india/fuxi"
    graphcast_model_dir: str = "/Users/hayden/code/ROMP/data/india/graphcast"
    gencast_model_dir: str = "/Users/hayden/code/ROMP/data/india/gencast"
    fuxi_s2s_model_dir: str = "/Users/hayden/code/ROMP/data/india/fuxi_s2s"


settings = Settings()

# ---------------------------------------------------------------------------
# Model registry — static metadata + per-deployment directory paths.
# Each entry maps to one selectable model in the UI. Models without a
# configured model_dir are excluded from the GET /models response.
# ---------------------------------------------------------------------------

def get_model_registry() -> list[dict]:
    candidates = [
        {
            "id": "aifs",
            "display_name": "AIFS",
            "model_type": "AIWP",
            "model_dir": settings.aifs_model_dir,
            "model_var": "tp",
            "unit_cvt": None,
            "file_pattern": "{}.nc",
            "probabilistic": False,
            "members": None,
            "init_days": "0,3",
            "date_filter_year": 2013,
            "start_date": "2013-05-01",
            "end_date": "2018-07-31",
            "start_year_clim": 2013,
            "end_year_clim": 2018,
        },
        {
            "id": "aifs_daily",
            "display_name": "AIFS (Daily)",
            "model_type": "AIWP",
            "model_dir": settings.aifs_daily_model_dir,
            "model_var": "tp",
            "unit_cvt": None,
            "file_pattern": "{}.nc",
            "probabilistic": False,
            "members": None,
            "init_days": "0,1,2,3,4,5,6",
            "start_date": "2019-05-01",
            "end_date": "2024-07-31",
            "start_year_clim": 1998,
            "end_year_clim": 2024,
        },
        {
            "id": "ifs",
            "display_name": "IFS-S2S",
            "model_type": "NWP",
            "model_dir": settings.ifs_model_dir,
            "model_var": "tp",
            "unit_cvt": None,
            "file_pattern": "{}.nc",
            "probabilistic": True,
            "members": "11",
            "init_days": "0,3",
            "date_filter_year": 2013,
            "start_date": "2004-05-01",
            "end_date": "2023-07-31",
            "start_year_clim": 1998,
            "end_year_clim": 2023,
        },
        {
            "id": "neuralgcm",
            "display_name": "NeuralGCM",
            "model_type": "AIWP",
            "model_dir": settings.neuralgcm_model_dir,
            "model_var": "tp",
            "unit_cvt": None,
            "file_pattern": "{}.nc",
            "probabilistic": True,
            "members": "51",
            "init_days": "0,3",
            "date_filter_year": 2013,
            "start_date": "1965-05-01",
            "end_date": "2024-07-31",
            "start_year_clim": 1998,
            "end_year_clim": 2024,
        },
        {
            "id": "fuxi",
            "display_name": "FuXi",
            "model_type": "AIWP",
            "model_dir": settings.fuxi_model_dir,
            "model_var": "tp",
            "unit_cvt": None,
            "file_pattern": "{}.nc",
            "probabilistic": False,
            "members": None,
            "init_days": "0,3",
            "date_filter_year": 2013,
            "start_date": "1965-05-01",
            "end_date": "2024-07-31",
            "start_year_clim": 1998,
            "end_year_clim": 2024,
        },
        {
            "id": "graphcast",
            "display_name": "GraphCast",
            "model_type": "AIWP",
            "model_dir": settings.graphcast_model_dir,
            "model_var": "tp",
            "unit_cvt": None,
            "file_pattern": "{}.nc",
            "probabilistic": False,
            "members": None,
            "init_days": "0,3",
            "date_filter_year": 2013,
            "start_date": "1965-05-01",
            "end_date": "2024-07-31",
            "start_year_clim": 1998,
            "end_year_clim": 2024,
        },
        {
            "id": "gencast",
            "display_name": "GenCast",
            "model_type": "AIWP",
            "model_dir": settings.gencast_model_dir,
            "model_var": "tp",
            "unit_cvt": None,
            "file_pattern": "{}.nc",
            "probabilistic": True,
            "members": "52",
            "init_days": "0,3",
            "date_filter_year": 2019,
            "start_date": "2019-05-01",
            "end_date": "2024-07-31",
            "start_year_clim": 1998,
            "end_year_clim": 2024,
        },
        {
            "id": "fuxi_s2s",
            "display_name": "FuXi-S2S",
            "model_type": "AIWP",
            "model_dir": settings.fuxi_s2s_model_dir,
            "model_var": "tp",
            "unit_cvt": None,
            "file_pattern": "{}.nc",
            "probabilistic": True,
            "members": "51",
            "init_days": "0,3",
            "date_filter_year": 2002,
            "start_date": "2002-05-01",
            "end_date": "2021-07-31",
            "start_year_clim": 1998,
            "end_year_clim": 2021,
        },
    ]
    # Only expose models that have a configured data directory.
    return [m for m in candidates if m["model_dir"]]


def get_demo_datasets() -> list[dict]:
    """Parse demo_obs_datasets setting into a list of dataset descriptors."""
    result = []
    for entry in settings.demo_obs_datasets.split(","):
        entry = entry.strip()
        if not entry or "=" not in entry:
            continue
        name, _, path = entry.partition("=")
        name, path = name.strip(), path.strip()
        if name and path:
            # Stable ID derived from name so it doesn't change across restarts.
            demo_id = "demo:" + name.lower().replace(" ", "-")
            result.append({"id": demo_id, "name": name, "obs_dir": path})
    return result
