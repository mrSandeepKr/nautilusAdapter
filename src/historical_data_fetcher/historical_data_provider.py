from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

from historical_data_fetcher.interfaces import HistoricalDataFetcher
from utility.nautilus_utility import empty_nautilus_frame
from historical_data_fetcher.historical_data_store import HistoricalDataStore

_NS_PER_SECOND = 1_000_000_000


def _date_to_ns(date_str: str, *, end: bool = False) -> int:
    dt = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
    if end:
        dt += timedelta(days=1) - timedelta(seconds=1)
    return int(dt.timestamp()) * _NS_PER_SECOND


def _filter_window(df: pd.DataFrame, from_date: str, to_date: str) -> pd.DataFrame:
    from_ns = _date_to_ns(from_date)
    to_ns = _date_to_ns(to_date, end=True)
    mask = (df["ts_init"] >= from_ns) & (df["ts_init"] <= to_ns)
    return df.loc[mask].reset_index(drop=True)


class HistoricalDataProvider:
    """Orchestrates storage lookup -> fetch -> save -> return.

    Owns the cache-or-fetch decision and all data-transformation logic
    (filtering, empty-frame creation).
    """

    def __init__(
        self,
        storage: HistoricalDataStore,
        fetcher: HistoricalDataFetcher,
    ) -> None:
        self._storage = storage
        self._fetcher = fetcher

    def fetch_historical_data(
        self,
        instrument: str,
        interval: str,
        from_date: str,
        to_date: str,
    ) -> pd.DataFrame:
        result = self._try_cache(instrument, interval, from_date, to_date)
        if result is not None:
            return result
        return self._fetch_and_store(instrument, interval, from_date, to_date)

    def _try_cache(
        self,
        instrument: str,
        interval: str,
        from_date: str,
        to_date: str,
    ) -> pd.DataFrame | None:
        path = self._storage.find(instrument, interval, from_date, to_date)
        if path is None:
            return None
        df = self._storage.read(path)
        return _filter_window(df, from_date, to_date)

    def _fetch_and_store(
        self,
        instrument: str,
        interval: str,
        from_date: str,
        to_date: str,
    ) -> pd.DataFrame:
        df = self._fetcher.fetch_historical_data(
            instrument, interval, from_date, to_date
        )
        if df.empty:
            return empty_nautilus_frame()
        self._storage.write_instrument(
            df, instrument, from_date, to_date, interval
        )
        return _filter_window(df, from_date, to_date)
