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


settings = Settings()
