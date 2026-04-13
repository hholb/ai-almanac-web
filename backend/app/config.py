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
    # Format: comma-separated "Name=path" or "Name=path|obs_file_pattern" pairs.
    # e.g. demo_obs_datasets: str = "India Demo=/data/obs/india,IMD 1°=/data/imd/1p0|data_{}.nc"
    demo_obs_datasets: str = (
        "India Demo (1964–2024)=/Users/hayden/code/ROMP/data/india/imd_rainfall_data/2p0|data_{}.nc,"
        "India Demo (2013–2020)=/Users/hayden/code/ROMP/demo/data/obs,"
        "Ethiopia (CHIRPS/IMERG 1998–2024)=/Users/hayden/code/ROMP/data/ethiopia/obs,"
        "IMD India 0.25° (1901–2024)=/Users/hayden/code/ROMP/data/india/imd_rainfall_data/0p25,"
        "IMD India 1.0° (1901–2024)=/Users/hayden/code/ROMP/data/india/imd_rainfall_data/1p0|data_{}.nc,"
        "IMD India 2.0° (1901–2024)=/Users/hayden/code/ROMP/data/india/imd_rainfall_data/2p0|data_{}.nc,"
        "IMD India 4.0° (1901–2024)=/Users/hayden/code/ROMP/data/india/imd_rainfall_data/4p0"
    )

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
            "unit_cvt": 1000,
            "file_pattern": "{}.nc",
            "probabilistic": False,
            "members": None,
            "init_days": "0,3",
            "date_filter_year": 2013,
            "start_date": "1964-05-01",
            "end_date": "2018-07-31",
            "start_year_clim": 1964,
            "end_year_clim": 2018,  # clim end capped to data end
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
    # Only expose models that have a configured data directory.
    return [m for m in candidates if m["model_dir"]]


def get_demo_datasets() -> list[dict]:
    """Parse demo_obs_datasets setting into a list of dataset descriptors.

    Each entry is "Name=path" or "Name=path|obs_file_pattern".
    The obs_file_pattern (e.g. "data_{}.nc") is passed to ROMP when a job is
    submitted against this dataset, overriding the default "{}.nc" pattern.
    """
    result = []
    for entry in settings.demo_obs_datasets.split(","):
        entry = entry.strip()
        if not entry or "=" not in entry:
            continue
        name, _, rest = entry.partition("=")
        name = name.strip()
        # rest may be "path" or "path|obs_file_pattern"
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
