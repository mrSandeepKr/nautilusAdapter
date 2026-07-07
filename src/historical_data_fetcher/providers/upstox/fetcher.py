from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from historical_data_fetcher.config import Settings, get_settings
from historical_data_fetcher.core.storage import instrument_path
from historical_data_fetcher.providers.upstox.auth import UpstoxAuthenticator
from historical_data_fetcher.providers.upstox.exceptions import (
    AuthenticationError,
    MissingAuthenticationError,
)

_BASE_URL = "https://api.upstox.com/v3/historical-candle"

# High-level interval -> (Upstox v3 unit, interval integer)
_INTERVAL_MAP: dict[str, tuple[str, int]] = {
    "1minute": ("minutes", 1),
    "3minute": ("minutes", 3),
    "5minute": ("minutes", 5),
    "15minute": ("minutes", 15),
    "30minute": ("minutes", 30),
    "1hour": ("hours", 1),
    "1day": ("days", 1),
    "1week": ("weeks", 1),
    "1month": ("months", 1),
}

# (unit, interval) -> bar duration in seconds, for computing ts_event (close)
_DURATION_SECONDS: dict[tuple[str, int], int] = {
    ("minutes", 1): 60,
    ("minutes", 3): 180,
    ("minutes", 5): 300,
    ("minutes", 15): 900,
    ("minutes", 30): 1800,
    ("hours", 1): 3600,
    ("days", 1): 86_400,
    ("weeks", 1): 604_800,
    ("months", 1): 2_592_000,  # 30-day nominal
}

_NANOS_PER_SECOND = 1_000_000_000


class UpstoxDataFetcher:
    """Fetches Upstox v3 historical candles and normalizes them to Nautilus
    Trader's strict Parquet bar schema.

    Implements :class:`historical_data_fetcher.core.interfaces.HistoricalDataFetcher`.
    """

    def __init__(self, authenticator: UpstoxAuthenticator, settings: Settings | None = None) -> None:
        self._authenticator = authenticator
        self._settings = settings or get_settings()

    def fetch_historical_data(
        self,
        instrument: str,
        interval: str,
        from_date: str,
        to_date: str,
    ) -> Path | None:
        unit, interval_val = self._resolve_interval(interval)
        rows = self._fetch_raw(instrument, unit, interval_val, from_date, to_date)
        if not rows:
            return None
        df = self._to_nautilus_frame(rows, unit, interval_val)
        path = instrument_path(
            instrument, from_date, to_date, interval, self._settings.DATA_DIR
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path, index=False)
        return path

    @staticmethod
    def _resolve_interval(interval: str) -> tuple[str, int]:
        try:
            return _INTERVAL_MAP[interval]
        except KeyError as exc:
            raise ValueError(
                f"Unsupported interval '{interval}'. "
                f"Supported: {sorted(_INTERVAL_MAP)}"
            ) from exc

    def _fetch_raw(
        self,
        instrument: str,
        unit: str,
        interval_val: int,
        from_date: str,
        to_date: str,
    ) -> list[list[Any]]:
        """Call Upstox API v3 historical-candle and return the candles list.

        GET {BASE_URL}/{instrumentKey}/{unit}/{interval}/{to_date}/{from_date}
        Each returned candle is
        ``[timestamp_iso, open, high, low, close, volume, open_interest]``.
        """
        access_token = self._authenticator.get_token()
        url = "/".join(
            (
                _BASE_URL,
                requests.utils.quote(instrument, safe="|"),
                unit,
                str(interval_val),
                to_date,
                from_date,
            )
        )
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
        }
        try:
            response = requests.get(url, headers=headers, timeout=30)
        except requests.RequestException as exc:
            raise AuthenticationError(f"Network error during fetch: {exc}") from exc

        if response.status_code in (401, 403):
            raise MissingAuthenticationError(
                f"Access token rejected (HTTP {response.status_code}): {response.text}"
            )
        if response.status_code != 200:
            raise AuthenticationError(
                f"Historical fetch failed (HTTP {response.status_code}): {response.text}"
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise AuthenticationError(f"Non-JSON response: {exc} / {response.text!r}") from exc

        data = body.get("data") or {}
        return list(data.get("candles", []) or [])

    @staticmethod
    def _to_nautilus_frame(rows: list[list[Any]], unit: str, interval_val: int) -> pd.DataFrame:
        duration_ns = _DURATION_SECONDS[(unit, interval_val)] * _NANOS_PER_SECOND

        ts_init_list: list[int] = []
        ts_event_list: list[int] = []
        opens: list[float] = []
        highs: list[float] = []
        lows: list[float] = []
        closes: list[float] = []
        volumes: list[int] = []

        for row in rows:
            # row == [timestamp_iso, open, high, low, close, volume, open_interest]
            ts_iso, o, h, l, c, v, _oi = row[:7]
            ts_init_ns = UpstoxDataFetcher._iso_to_nanos(ts_iso)
            ts_init_list.append(ts_init_ns)
            ts_event_list.append(ts_init_ns + duration_ns)
            opens.append(float(o))
            highs.append(float(h))
            lows.append(float(l))
            closes.append(float(c))
            volumes.append(int(v))

        df = pd.DataFrame(
            {
                "ts_event": pd.Series(ts_event_list, dtype="uint64[pyarrow]"),
                "ts_init": pd.Series(ts_init_list, dtype="uint64[pyarrow]"),
                "open": pd.Series(opens, dtype="float64[pyarrow]"),
                "high": pd.Series(highs, dtype="float64[pyarrow]"),
                "low": pd.Series(lows, dtype="float64[pyarrow]"),
                "close": pd.Series(closes, dtype="float64[pyarrow]"),
                "volume": pd.Series(volumes, dtype="uint64[pyarrow]"),
            }
        )
        df = df.sort_values("ts_init").reset_index(drop=True)
        return df

    @staticmethod
    def _iso_to_nanos(iso_str: str) -> int:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.astimezone(timezone.utc).timestamp() * _NANOS_PER_SECOND)