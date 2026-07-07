from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

RATE_LIMIT_REQUESTS_PER_SECOND = 8
RATE_LIMIT_REQUESTS_PER_MINUTE = 450


class UpstoxSettings(BaseSettings):
    """Upstox-specific configuration sourced from ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATA_DIR: Path

    UPSTOX_PHONE_NUMBER: str
    UPSTOX_PIN_CODE: str
    UPSTOX_TOTP_SECRET: str
    UPSTOX_API_KEY: str
    UPSTOX_API_SECRET: str
    UPSTOX_REDIRECT_URI: str

    UPSTOX_BASE_URL: str = Field(
        default="https://api.upstox.com",
        description="Upstox API base URL (without path segments).",
    )

    # -- computed URL properties ------------------------------------------------

    @property
    def historical_candle_url(self) -> str:
        """Full URL for the historical-candle endpoint."""
        return f"{self.UPSTOX_BASE_URL}/v3/historical-candle"

    @property
    def authorize_url(self) -> str:
        """Full URL for the OAuth authorization dialog."""
        return f"{self.UPSTOX_BASE_URL}/v2/login/authorization/dialog"

    @property
    def token_url(self) -> str:
        """Full URL for the OAuth token exchange endpoint."""
        return f"{self.UPSTOX_BASE_URL}/v2/login/authorization/token"

    # -- derived paths ----------------------------------------------------------

    @property
    def upstox_access_token_path(self) -> Path:
        return Path(self.DATA_DIR) / "upstox_access_token.txt"


_settings: UpstoxSettings | None = None


def get_upstox_settings() -> UpstoxSettings:
    """Return a cached :class:`UpstoxSettings` singleton.

    The first call reads ``.env``, ensures :attr:`DATA_DIR` exists, and
    stores the instance. Subsequent calls reuse it.
    """
    global _settings
    if _settings is None:
        settings = UpstoxSettings()
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        _settings = settings
    return _settings
