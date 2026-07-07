from __future__ import annotations

import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from historical_data_fetcher.core.interfaces import HistoricalDataFetcher

_NS_PER_SECOND = 1_000_000_000

_FILENAME_RE = re.compile(
    r"^(?P<from>\d{4}-\d{2}-\d{2})_(?P<to>\d{4}-\d{2}-\d{2})_(?P<candle>.+)\.parquet$"
)

_NAUTILUS_COLUMNS = (
    "ts_event",
    "ts_init",
    "open",
    "high",
    "low",
    "close",
    "volume",
)


def sanitize_instrument(instrument: str) -> str:
    """Apply the canonical path sanitization rule: ``|`` -> ``_``, space -> ``-``."""
    return instrument.replace("|", "_").replace(" ", "-")


def instrument_dir(instrument: str, data_dir: Path) -> Path:
    """Return ``data_dir / <sanitized_instrument>`` (without writing anything)."""
    return Path(data_dir) / sanitize_instrument(instrument)


def range_filename(from_date: str, to_date: str, candle_length: str) -> str:
    """Return the canonical file name ``<from>_<to>_<candle>.parquet``."""
    return f"{from_date}_{to_date}_{candle_length}.parquet"


def instrument_path(
    instrument: str,
    from_date: str,
    to_date: str,
    candle_length: str,
    data_dir: Path,
) -> Path:
    """Return the exact Parquet path a fetcher must write and the store must read.

    This is the ONE place that builds on-disk Parquet paths from logical
    arguments. Both the Upstox fetcher (write side) and ``LocalDataStore``
    (read side) call this helper so the two never disagree.
    """
    return instrument_dir(instrument, data_dir) / range_filename(
        from_date, to_date, candle_length
    )


def _parse_filename(name: str) -> tuple[str, str, str] | None:
    match = _FILENAME_RE.match(name)
    if match is None:
        return None
    return match.group("from"), match.group("to"), match.group("candle")


def find_containing_file(
    instrument: str,
    from_date: str,
    to_date: str,
    candle_length: str,
    data_dir: Path,
) -> Path | None:
    """Return the tightest-fit stored Parquet covering the requested range, or ``None``.

    A file is a hit iff its ``candleLength`` matches exactly and its stored
    span *contains or equals* the requested span (i.e. ``stored_from <= from``
    AND ``stored_to >= to``). Among multiple hits the one with the smallest
    stored span (tightest fit) is returned to minimize rows read.
    """
    directory = instrument_dir(instrument, data_dir)
    if not directory.is_dir():
        return None

    best_span: int | None = None
    best_path: Path | None = None
    for entry in directory.iterdir():
        if entry.suffix != ".parquet" or not entry.is_file():
            continue
        parsed = _parse_filename(entry.name)
        if parsed is None:
            continue
        stored_from, stored_to, stored_candle = parsed
        if stored_candle != candle_length:
            continue
        if stored_from > from_date or stored_to < to_date:
            continue
        span = (
            datetime.fromisoformat(stored_to)
            - datetime.fromisoformat(stored_from)
        ).days
        if best_span is None or span < best_span:
            best_span = span
            best_path = entry
    return best_path


def _date_to_ns(date_str: str, *, end: bool = False) -> int:
    """Convert a ``YYYY-MM-DD`` date string to UNIX nanoseconds (UTC)."""
    dt = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
    if end:
        dt += timedelta(days=1) - timedelta(seconds=1)
    return int(dt.timestamp()) * _NS_PER_SECOND


def _empty_nautilus_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_event": pd.Series([], dtype="uint64[pyarrow]"),
            "ts_init": pd.Series([], dtype="uint64[pyarrow]"),
            "open": pd.Series([], dtype="float64[pyarrow]"),
            "high": pd.Series([], dtype="float64[pyarrow]"),
            "low": pd.Series([], dtype="float64[pyarrow]"),
            "close": pd.Series([], dtype="float64[pyarrow]"),
            "volume": pd.Series([], dtype="uint64[pyarrow]"),
        }
    )


def _filter_window(df: pd.DataFrame, from_date: str, to_date: str) -> pd.DataFrame:
    from_ns = _date_to_ns(from_date)
    to_ns = _date_to_ns(to_date, end=True)
    mask = (df["ts_init"] >= from_ns) & (df["ts_init"] <= to_ns)
    return df.loc[mask].reset_index(drop=True)


class LocalDataStore:
    """Offline-first Parquet cache wrapping a :class:`HistoricalDataFetcher`.

    Serves reads from disk when a stored file satisfies the requested range
    (per the containment rule in :func:`find_containing_file`); otherwise
    delegates to the wrapped fetcher, which writes the new Parquet back into
    the store, then reads it back.
    """

    def __init__(
        self,
        fetcher: HistoricalDataFetcher,
        data_dir: Path,
    ) -> None:
        self._fetcher = fetcher
        self._data_dir = Path(data_dir)

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    def get_historical_data(
        self,
        instrument: str,
        interval: str,
        from_date: str,
        to_date: str,
    ) -> pd.DataFrame:
        """Return candles for ``[from_date, to_date]`` as a Nautilus DataFrame.

        Cache hits incur neither HTTP nor auth: rows are read from the stored
        Parquet and filtered to the requested window. Cache misses delegate to
        the wrapped fetcher, which writes a fresh Parquet under the instruments
        directory; the store then reads it back.
        """
        path = find_containing_file(
            instrument, from_date, to_date, interval, self._data_dir
        )
        if path is not None:
            df = pd.read_parquet(path)
            return _filter_window(df, from_date, to_date)

        result = self._fetcher.fetch_historical_data(
            instrument, interval, from_date, to_date
        )
        if result is None:
            return _empty_nautilus_frame()
        df = pd.read_parquet(result)
        return _filter_window(df, from_date, to_date)

    def exists(
        self,
        instrument: str,
        interval: str,
        from_date: str,
        to_date: str,
    ) -> bool:
        """Cheap containment check: does a stored file already cover this range?"""
        return (
            find_containing_file(
                instrument, from_date, to_date, interval, self._data_dir
            )
            is not None
        )

    def invalidate(
        self,
        instrument: str,
        from_date: str,
        to_date: str,
        candle_length: str,
    ) -> None:
        """Remove the stored file matching the *exact* requested key (if any).

        Uses the exact filename (not the containment rule) so callers can
        selectively drop a single stale span without touching larger files
        that happen to cover it.
        """
        path = instrument_path(
            instrument, from_date, to_date, candle_length, self._data_dir
        )
        if path.exists():
            path.unlink()

    def purge_instrument(self, instrument: str) -> None:
        """Delete the entire instrument directory and everything under it."""
        directory = instrument_dir(instrument, self._data_dir)
        if directory.exists():
            shutil.rmtree(directory)