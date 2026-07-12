from __future__ import annotations

from decimal import Decimal

from provider.screener.bhavcopy.client import BhavcopyClient
from provider.screener.bhavcopy.data_fetcher import BhavcopyDataFetcher
from provider.screener.nse_data.client import NseData
from provider.upstox.instrument_store import InstrumentStore

from backtester.core.models import BenchmarkEntry, UniverseEntry


def _resolve_entry(store: InstrumentStore, symbol: str) -> UniverseEntry | None:
    results = store.search(symbol, limit=20)
    info = None
    for r in results:
        if r.get("trading_symbol", "").upper() == symbol.upper() and r.get("segment") == "NSE_EQ":
            info = r
            break
    if info is None:
        for r in results:
            if r.get("trading_symbol", "").upper() == symbol.upper():
                info = r
                break
    if info is None and results:
        info = results[0]
    if info is None:
        return None
    return UniverseEntry(
        symbol=symbol,
        upstox_key=info["instrument_key"],
        instrument_id_str=f"{symbol}.NSE",
        tick_size=Decimal(str(info.get("tick_size", 5))) / Decimal("100"),
        lot_size=int(info.get("lot_size", 1)),
        isin=info.get("isin"),
    )


def _benchmark_entry(store: InstrumentStore) -> BenchmarkEntry:
    upstox_key = store.resolve("NIFTY")
    return BenchmarkEntry(
        symbol="NIFTY",
        upstox_key=upstox_key or "NSE_INDEX|Nifty 50",
        instrument_id_str="NIFTY.NSE",
    )


def build_universe_from_symbols(symbols: list[str]) -> list[UniverseEntry]:
    store = InstrumentStore()
    return [e for s in symbols if (e := _resolve_entry(store, s)) is not None]


def build_universe_top_volatile(
    n: int = 200,
    window: int = 20,
) -> tuple[list[UniverseEntry], BenchmarkEntry]:
    bhavcopy = BhavcopyClient(BhavcopyDataFetcher())
    top = bhavcopy.top_volatile(n=n, window=window)
    symbols = list(top["symbol"])
    store = InstrumentStore()
    entries = [e for s in symbols if (e := _resolve_entry(store, s)) is not None]
    return entries, _benchmark_entry(store)


def build_universe_liquid(
    n: int = 200,
    min_trade_value: float = 50_000_000,
) -> tuple[list[UniverseEntry], BenchmarkEntry]:
    bhavcopy = BhavcopyClient(BhavcopyDataFetcher())
    latest = bhavcopy.latest_bhavcopy()
    if latest.empty:
        return [], _benchmark_entry(InstrumentStore())

    equity_series = ("EQ", "BE", "BZ")
    df = latest[latest["SctySrs"].isin(equity_series)].copy()
    df = df[df["TtlTrfVal"] >= min_trade_value]
    df = df.sort_values("TtlTrfVal", ascending=False).head(n)

    symbols = list(df["TckrSymb"])
    store = InstrumentStore()
    entries = []
    for s in symbols:
        e = _resolve_entry_eq(store, s)
        if e is not None:
            entries.append(e)
        if len(entries) >= n:
            break
    return entries, _benchmark_entry(store)


def _resolve_entry_eq(store: InstrumentStore, symbol: str) -> UniverseEntry | None:
    results = store.search_exact(symbol)
    for r in results:
        if r.get("segment") == "NSE_EQ":
            return UniverseEntry(
                symbol=symbol,
                upstox_key=r["instrument_key"],
                instrument_id_str=f"{symbol}.NSE",
                tick_size=Decimal(str(r.get("tick_size", 5))) / Decimal("100"),
                lot_size=int(r.get("lot_size", 1)),
                isin=r.get("isin"),
            )
    return None


def build_universe_nifty50() -> tuple[list[UniverseEntry], BenchmarkEntry]:
    store = InstrumentStore()
    symbols = NseData.nifty_50()
    entries = [e for s in symbols if (e := _resolve_entry_eq(store, s)) is not None]
    return entries, _benchmark_entry(store)
