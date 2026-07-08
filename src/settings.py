from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Generic application-wide settings sourced from ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATA_DIR: Path


_app_settings: AppSettings | None = None


def get_app_settings() -> AppSettings:
    global _app_settings
    if _app_settings is None:
        settings = AppSettings()
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        _app_settings = settings
    return _app_settings
