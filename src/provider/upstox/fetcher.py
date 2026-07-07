from __future__ import annotations

import urllib.parse
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd

from utility.nautilus_utility import empty_nautilus_frame
from provider.upstox.settings import UpstoxSettings
from provider.upstox.client import _ClientProtocol
from provider.upstox.exceptions import (
    AuthenticationError,
    MissingAuthenticationError,
)


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

_DURATION_SECONDS: dict[tuple[str, int], int] = {
    ("minutes", 1): 60,
    ("minutes", 3): 180,
    ("minutes", 5): 300,
    ("minutes", 15): 900,
    ("minutes", 30): 1800,
    ("hours", 1): 3600,
    ("days", 1): 86_400,
    ("weeks", 1): 604_800,
    ("months", 1): 2_592_000,
}

_NANOS_PER_SECOND = 1_000_000_000


class UpstoxDataFetcher:
    """Pure data fetcher.  Given an authenticated client it fetches, normalises,
    and persists Upstox v3 historical candles as Nautilus Parquet files.

    The fetcher owns zero infrastructure — no auth management, no rate-limit
    logic, no raw ``requests`` calls.  All of that lives in the ``client``.
    """

    def __init__(
        self,
        client: _ClientProtocol,
        settings: UpstoxSettings,
    ) -> None:
        self._client = client
        self._settings = settings

    # -- public API ----------------------------------------------------------------

    def fetch_historical_data(
        self,
        instrument: str,
        interval: str,
        from_date: str,
        to_date: str,
    ) -> pd.DataFrame:
        unit, interval_val = self._resolve_interval(interval)
        all_rows: list[list[Any]] = []
        for chunk_from, chunk_to in self._date_chunks(
            unit, interval_val, from_date, to_date
        ):
            rows = self._fetch_raw(
                instrument, unit, interval_val, chunk_from, chunk_to
            )
            all_rows.extend(rows)
        if not all_rows:
            return empty_nautilus_frame()
        return self._to_nautilus_frame(all_rows, unit, interval_val)

    # -- interval resolution -------------------------------------------------------

    def _resolve_interval(self, interval: str) -> tuple[str, int]:
        try:
            return _INTERVAL_MAP[interval]
        except KeyError as exc:
            raise ValueError(
                f"Unsupported interval '{interval}'. "
                f"Supported: {sorted(_INTERVAL_MAP)}"
            ) from exc

    # -- date chunking (respects Upstox API per-request limits) --------------------

    def _date_chunks(
        self,
        unit: str,
        interval_val: int,
        from_date: str,
        to_date: str,
    ) -> list[tuple[str, str]]:
        max_days = self._max_chunk_days(unit, interval_val)
        if max_days is None:
            return [(from_date, to_date)]
        if max_days == 30:
            return self._month_chunks(from_date, to_date)
        return self._day_chunks(from_date, to_date, max_days)

    def _max_chunk_days(self, unit: str, interval_val: int) -> int | None:
        if unit == "minutes":
            return 30 if interval_val <= 15 else 90
        if unit == "hours":
            return 90
        if unit == "days":
            return 3650
        return None

    def _month_chunks(
        self, from_date: str, to_date: str
    ) -> list[tuple[str, str]]:
        start = date.fromisoformat(from_date)
        end = date.fromisoformat(to_date)
        ranges: list[tuple[str, str]] = []
        cur = start.replace(day=1)
        while cur <= end:
            _, last_day = monthrange(cur.year, cur.month)
            chunk_end = date(cur.year, cur.month, last_day)
            if chunk_end > end:
                chunk_end = end
            ranges.append((cur.isoformat(), chunk_end.isoformat()))
            y = cur.year + (cur.month // 12)
            m = (cur.month % 12) + 1
            cur = date(y, m, 1)
        return ranges

    def _day_chunks(
        self, from_date: str, to_date: str, chunk_size: int
    ) -> list[tuple[str, str]]:
        ranges: list[tuple[str, str]] = []
        cur = date.fromisoformat(from_date)
        end = date.fromisoformat(to_date)
        while cur <= end:
            chunk_end = min(cur + timedelta(days=chunk_size - 1), end)
            ranges.append((cur.isoformat(), chunk_end.isoformat()))
            cur = chunk_end + timedelta(days=1)
        return ranges

    # -- raw HTTP fetch ------------------------------------------------------------

    def _fetch_raw(
        self,
        instrument: str,
        unit: str,
        interval_val: int,
        from_date: str,
        to_date: str,
    ) -> list[list[Any]]:
        access_token = self._client.authenticate()
        url = "/".join(
            (
                self._settings.historical_candle_url,
                urllib.parse.quote(instrument, safe="|"),
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
            response = self._client.http.get(url, headers=headers)
        except Exception as exc:
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
            raise AuthenticationError(
                f"Non-JSON response: {exc} / {response.text!r}"
            ) from exc

        data = body.get("data") or {}
        return list(data.get("candles", []) or [])

    # -- response normalisation ----------------------------------------------------

    def _to_nautilus_frame(
        self, rows: list[list[Any]], unit: str, interval_val: int
    ) -> pd.DataFrame:
        duration_ns = _DURATION_SECONDS[(unit, interval_val)] * _NANOS_PER_SECOND

        ts_init_list: list[int] = []
        ts_event_list: list[int] = []
        opens: list[float] = []
        highs: list[float] = []
        lows: list[float] = []
        closes: list[float] = []
        volumes: list[int] = []

        for row in rows:
            ts_iso, o, h, l, c, v, _oi = row[:7]
            ts_init_ns = self._iso_to_nanos(ts_iso)
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

    def _iso_to_nanos(self, iso_str: str) -> int:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.astimezone(timezone.utc).timestamp() * _NANOS_PER_SECOND)
