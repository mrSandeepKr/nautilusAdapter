from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from provider.screener.bhavcopy.data_fetcher import BhavcopyDataFetcher

_EQUITY_SERIES = ("EQ", "BE", "BZ")


class BhavcopyClient:

    def __init__(self, data_fetcher: BhavcopyDataFetcher) -> None:
        self._fetcher = data_fetcher

    def latest_bhavcopy(self) -> pd.DataFrame:
        d = self._fetcher.latest_date()
        return self._fetcher.load_range(d, d)

    def volatility(self, symbol: str, window: int = 20) -> pd.Series:
        end = self._fetcher.latest_date()
        start = end - timedelta(days=_lookback_calendar_days(window))
        df = self._fetcher.load_symbol(symbol, start, end)
        if df.empty or len(df) < 2:
            return pd.Series(dtype="float64")
        df = df.sort_values("TradDt")
        closes = df["ClsPric"].values
        returns = np.log(closes[1:] / closes[:-1])
        vol_arr = (
            pd.Series(returns).rolling(window).std().values * np.sqrt(252)
        )
        return pd.Series(vol_arr, index=df["TradDt"].iloc[1:], name=symbol)

    def top_volatile(
        self,
        n: int = 200,
        window: int = 20,
        universe: list[str] | None = None,
    ) -> pd.DataFrame:
        cols = ["symbol", "volatility", "close", "close_date"]
        end = self._fetcher.latest_date()
        start = end - timedelta(days=_lookback_calendar_days(window))
        df = self._fetcher.load_range(start, end)
        if df.empty:
            return pd.DataFrame(columns=cols)

        df = df[df["SctySrs"].isin(_EQUITY_SERIES)]
        if universe is not None:
            if not universe:
                return pd.DataFrame(columns=cols)
            universe_upper = {s.upper() for s in universe}
            df = df[df["TckrSymb"].isin(universe_upper)]

        pivoted = df.pivot_table(
            index="TradDt", columns="TckrSymb", values="ClsPric", aggfunc="first"
        )
        pivoted = pivoted.sort_index()
        if len(pivoted) < 2:
            return pd.DataFrame(columns=cols)

        returns = np.log(pivoted / pivoted.shift(1))
        vol_series = returns.rolling(window).std() * np.sqrt(252)
        latest_vol = vol_series.iloc[-1].dropna()
        latest_close = pivoted.iloc[-1]
        close_date = str(pivoted.index[-1])

        result = pd.DataFrame({
            "symbol": latest_vol.index,
            "volatility": latest_vol.values,
            "close": latest_close[latest_vol.index].values,
        })
        result["close_date"] = close_date
        result = result.sort_values("volatility", ascending=False).head(n)
        return result.reset_index(drop=True)

    def gainers(self, n: int = 10) -> pd.DataFrame:
        return self._top_movers(n, ascending=False)

    def losers(self, n: int = 10) -> pd.DataFrame:
        return self._top_movers(n, ascending=True)

    def _top_movers(self, n: int, ascending: bool) -> pd.DataFrame:
        df = self.latest_bhavcopy()
        if df.empty:
            return pd.DataFrame(columns=["symbol", "pct_change", "close"])
        df = df[df["SctySrs"].isin(_EQUITY_SERIES)].copy()
        df["pct_change"] = (
            (df["ClsPric"] - df["PrvsClsgPric"]) / df["PrvsClsgPric"] * 100
        )
        result = (
            df.nsmallest(n, "pct_change")
            if ascending
            else df.nlargest(n, "pct_change")
        )
        return result[["TckrSymb", "pct_change", "ClsPric"]].rename(
            columns={"TckrSymb": "symbol", "ClsPric": "close"}
        ).reset_index(drop=True)


def _lookback_calendar_days(window: int) -> int:
    return int(window * 1.5) + 10
