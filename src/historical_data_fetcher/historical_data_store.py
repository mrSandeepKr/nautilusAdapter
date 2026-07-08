from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

from utility.file_storage import FileStorage

_FILENAME_RE = re.compile(
    r"^(?P<from>\d{4}-\d{2}-\d{2})_(?P<to>\d{4}-\d{2}-\d{2})_(?P<candle>.+)\.parquet$"
)


class HistoricalDataStore:
    """Parquet file-system wrapper over FileStorage.

    Knows only about paths and Parquet I/O.  No data transformation or
    fetch orchestration.

    The underlying :attr:`storage` provides low-level ``set``/``get``/``delete``
    access (:class:`~utility.file_storage.FileStorage`) for callers that
    need raw file operations outside of the Parquet convention.
    """

    def __init__(self) -> None:
        self._storage = FileStorage("historical_data")

    @property
    def data_dir(self) -> Path:
        return self._storage.root

    @property
    def storage(self) -> FileStorage:
        return self._storage

    # -- internal helpers --------------------------------------------------------

    @staticmethod
    def _range_filename(from_date: str, to_date: str, candle_length: str) -> str:
        return f"{from_date}_{to_date}_{candle_length}.parquet"

    def _instrument_path(
        self,
        instrument: str,
        from_date: str,
        to_date: str,
        candle_length: str,
    ) -> Path:
        return self._storage.root / instrument / self._range_filename(
            from_date, to_date, candle_length
        )

    @staticmethod
    def _parse_filename(name: str) -> tuple[str, str, str] | None:
        match = _FILENAME_RE.match(name)
        if match is None:
            return None
        return match.group("from"), match.group("to"), match.group("candle")

    def _find_containing_file(
        self,
        instrument: str,
        from_date: str,
        to_date: str,
        candle_length: str,
    ) -> Path | None:
        best_span: int | None = None
        best_path: Path | None = None
        for entry in self._storage.list(f"{instrument}/*.parquet"):
            parsed = self._parse_filename(entry.name)
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

    # -- public API --------------------------------------------------------------

    def find(
        self,
        instrument: str,
        interval: str,
        from_date: str,
        to_date: str,
    ) -> Path | None:
        return self._find_containing_file(
            instrument, from_date, to_date, interval
        )

    def read(self, path: Path) -> pd.DataFrame:
        return pd.read_parquet(path)

    def write(self, df: pd.DataFrame, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path, index=False)
        return path

    def write_instrument(
        self,
        df: pd.DataFrame,
        instrument: str,
        from_date: str,
        to_date: str,
        candle_length: str,
    ) -> Path:
        path = self._instrument_path(instrument, from_date, to_date, candle_length)
        return self.write(df, path)

    def exists(
        self,
        instrument: str,
        interval: str,
        from_date: str,
        to_date: str,
    ) -> bool:
        return (
            self._find_containing_file(
                instrument, from_date, to_date, interval
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
        path = self._instrument_path(
            instrument, from_date, to_date, candle_length
        )
        self._storage.delete(
            str(path.relative_to(self._storage.root))
        )

    def purge_instrument(self, instrument: str) -> None:
        dir_path = self._storage.root / instrument
        if dir_path.exists():
            shutil.rmtree(dir_path)
