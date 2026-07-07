from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import pandas as pd

from historical_data_fetcher.interfaces import HistoricalDataFetcher
from provider.upstox.settings import (
    RATE_LIMIT_REQUESTS_PER_MINUTE,
    RATE_LIMIT_REQUESTS_PER_SECOND,
    get_upstox_settings,
)
from provider.upstox.auth import UpstoxAuthenticator
from provider.realtime_http_client import RealtimeHttpClient


class _ClientProtocol(Protocol):
    def authenticate(self, force_refresh: bool = False) -> str: ...

    @property
    def http(self) -> RealtimeHttpClient: ...


from provider.upstox.fetcher import UpstoxDataFetcher


class UpstoxClient(HistoricalDataFetcher):
    """Unified Upstox client with init/auth/fetch_data lifecycle.

    Owns infrastructure (auth, rate-limited HTTP) and delegates data-fetch
    to a pure :class:`UpstoxDataFetcher`.

    Conforms to :class:`HistoricalDataFetcher` Protocol so it can be used
    anywhere a provider-agnostic fetcher is expected (e.g.
    ``LocalDataStore``).
    """

    def __init__(self) -> None:
        self._settings = get_upstox_settings()

        self._http = RealtimeHttpClient(
            requests_per_second=RATE_LIMIT_REQUESTS_PER_SECOND,
            requests_per_minute=RATE_LIMIT_REQUESTS_PER_MINUTE,
        )

        self._authenticator = UpstoxAuthenticator(self._settings)

        self._fetcher = UpstoxDataFetcher(
            client=self,
            settings=self._settings,
        )

    # -- infrastructure --------------------------------------------------------

    @property
    def http(self) -> RealtimeHttpClient:
        """Provider-agnostic HTTP client with built-in rate limiting."""
        return self._http

    # -- auth ------------------------------------------------------------------

    def authenticate(self, force_refresh: bool = False) -> str:
        """Obtain (or reuse) a valid Upstox access token."""
        return self._authenticator.get_token(force_refresh=force_refresh)

    # -- fetch_data (conforms to HistoricalDataFetcher) ------------------------

    def fetch_historical_data(
        self,
        instrument: str,
        interval: str,
        from_date: str,
        to_date: str,
    ) -> pd.DataFrame:
        return self._fetcher.fetch_historical_data(
            instrument, interval, from_date, to_date
        )
