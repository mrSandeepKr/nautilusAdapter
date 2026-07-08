from __future__ import annotations

import io
from datetime import date, timedelta

import pandas as pd
from nselib import capital_market

from utility.file_storage import FileStorage

_CALENDAR_DAYS_BACKFILL = 280


class BhavcopyDataFetcher:

    def __init__(self) -> None:
        self._storage = FileStorage("bhavcopy")
        self._backfill()

    def fetch_range(self, start: date, end: date) -> None:
        cur = start
        while cur <= end:
            if cur.weekday() < 5:
                key = f"{cur.isoformat()}.parquet"
                if not self._storage.exists(key):
                    try:
                        df = capital_market.bhav_copy_equities(
                            trade_date=cur.strftime("%d-%m-%Y"),
                        )
                        if not df.empty:
                            self._write_parquet(key, df)
                    except Exception:
                        pass
            cur += timedelta(days=1)

    def load_range(self, start: date, end: date) -> pd.DataFrame:
        chunks: list[pd.DataFrame] = []
        cur = start
        while cur <= end:
            key = f"{cur.isoformat()}.parquet"
            data = self._storage.get(key)
            if data is not None:
                df = pd.read_parquet(io.BytesIO(data))
                chunks.append(df)
            cur += timedelta(days=1)
        if not chunks:
            return pd.DataFrame()
        return pd.concat(chunks, ignore_index=True)

    def load_symbol(
        self, symbol: str, start: date, end: date
    ) -> pd.DataFrame:
        df = self.load_range(start, end)
        if df.empty:
            return df
        return df[df["TckrSymb"] == symbol.upper()].reset_index(drop=True)

    def latest_date(self) -> date:
        dates = self.available_dates()
        return dates[-1] if dates else date(2000, 1, 1)

    def available_dates(self) -> list[date]:
        files = self._storage.list("*.parquet")
        result: list[date] = []
        for f in files:
            try:
                result.append(date.fromisoformat(f.stem))
            except ValueError:
                pass
        return sorted(result)

    def refresh(self) -> None:
        self._backfill()

    def _backfill(self) -> None:
        today = date.today()
        latest = self.latest_date()
        if latest.year == 2000:
            start = today - timedelta(days=_CALENDAR_DAYS_BACKFILL)
            self.fetch_range(start, today)
        elif latest < today:
            self.fetch_range(latest + timedelta(days=1), today)

    def _write_parquet(self, key: str, df: pd.DataFrame) -> None:
        buf = io.BytesIO()
        df.to_parquet(buf)
        self._storage.set(key, buf.getvalue())
