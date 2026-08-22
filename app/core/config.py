from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "GIBDD Eyewitness API"

    db_name: str = Field(default="gibdd_local", validation_alias="DB_NAME")
    db_user: str = Field(default="postgres", validation_alias="DB_USER")
    db_password: str = Field(default="postgres", validation_alias="DB_PASSWORD")
    db_host: str = Field(default="127.0.0.1", validation_alias="DB_HOST")
    db_port: int = Field(default=5432, validation_alias="DB_PORT")

    media_storage_dir: str = Field(
        default="storage/media",
        validation_alias="MEDIA_STORAGE_DIR",
    )
    fcm_project_id: str | None = Field(default=None, validation_alias="FCM_PROJECT_ID")
    fcm_service_account_file: str | None = Field(
        default=None,
        validation_alias="FCM_SERVICE_ACCOUNT_FILE",
    )
    push_request_timeout_seconds: float = Field(
        default=3.0,
        validation_alias="PUSH_REQUEST_TIMEOUT_SECONDS",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
