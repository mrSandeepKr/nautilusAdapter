from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Single source of truth for the package.

    Reads all configuration from the session's ``.env`` file. Required
    variables raise at instantiation if missing. Provider modules consume
    the resulting :class:`Settings` instance — never ``os.environ`` directly.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATA_DIR: Path = Field(
        default=Path("./data_fetched/"),
        description="Root directory where fetched Parquet files are stored.",
    )

    UPSTOX_PHONE_NUMBER: str
    UPSTOX_PIN_CODE: str
    UPSTOX_TOTP_SECRET: str
    UPSTOX_API_KEY: str
    UPSTOX_API_SECRET: str
    UPSTOX_REDIRECT_URI: str

    @property
    def upstox_access_token_path(self) -> Path:
        return Path(self.DATA_DIR) / "upstox_access_token.txt"


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance.

    The first call reads the ``.env`` file, ensures :attr:`DATA_DIR` exists,
    and stores the singleton. Subsequent calls reuse it.
    """
    global _settings
    if _settings is None:
        settings = Settings()
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        _settings = settings
    return _settings