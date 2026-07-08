"""Thin wrapper: fetch 5-min candles since 2022-01-01 for TOP_VOLATILE_N NSE equities."""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone

import pandas as pd

from historical_data_fetcher import HistoricalDataProvider, HistoricalDataStore
from provider.screener import BhavcopyClient, BhavcopyDataFetcher
from provider.upstox import UpstoxClient
from provider.upstox.instrument_store import InstrumentStore

_NS = 1_000_000_000
TOP_VOLATILE_N = 200


def main() -> None:
    print(f"[1/3] Computing top {TOP_VOLATILE_N} volatile stocks from NSE bhavcopy...")
    bhavcopy = BhavcopyClient(BhavcopyDataFetcher())
    top = bhavcopy.top_volatile(n=TOP_VOLATILE_N)
    symbols: list[str] = top["symbol"].tolist()
    print(f"       Found {len(symbols)} symbols "
          f"(volatility {top['volatility'].min():.2%} – {top['volatility'].max():.2%})")

   
    # 2. Resolve each symbol to Upstox instrument key
    print("\n[2/3] Resolving Upstox instrument keys via master contract...")
    store = InstrumentStore(exchange="NSE")
    instruments: list[tuple[str, str]] = []
    for sym in symbols:
        key = store.resolve(sym)
        if key:
            instruments.append((sym, key))
    print(f"       Resolved {len(instruments)}/{len(symbols)} symbols")

    
    # 3. Wire up the provider and fetch
    print("\n[3/3] Fetching 5-minute candles (cached via Parquet)...")
    provider = HistoricalDataProvider(
        storage=HistoricalDataStore(),
        fetcher=UpstoxClient(),
    )

    from_date = "2022-01-01"
    to_date = date.today().isoformat()
    interval = "5minute"

    records: list[dict] = []
    for sym, inst_key in instruments:
        try:
            df = provider.fetch_historical_data(inst_key, interval, from_date, to_date)
            rows = len(df)
            if rows:
                first = _ts_to_dt(df["ts_init"].iloc[0])
                last = _ts_to_dt(df["ts_init"].iloc[-1])
                print(f"  ✓ {sym:20s}  {rows:>8,} rows  [{first.date()} – {last.date()}]")
                records.append({"symbol": sym, "rows": rows, "first_date": first, "last_date": last})
            else:
                print(f"  – {sym:20s}  empty")
                records.append({"symbol": sym, "rows": 0, "first_date": None, "last_date": None})
        except Exception as e:
            print(f"  ✗ {sym:20s}  {e}")
            records.append({"symbol": sym, "rows": 0, "first_date": None, "last_date": None, "error": str(e)})

    _print_verification_summary(records)


def _ts_to_dt(ts_ns: int) -> datetime:
    return datetime.fromtimestamp(ts_ns / _NS, tz=timezone.utc)


def _print_verification_summary(records: list[dict]) -> None:
    print("\n" + "=" * 72)
    print("VERIFICATION SUMMARY")
    print("=" * 72)
    stats = pd.DataFrame(records)

    total = len(stats)
    with_data = (stats["rows"] > 0).sum()
    empty = (stats["rows"] == 0).sum()
    total_rows = int(stats["rows"].sum())

    print(f"  Instruments attempted : {total}")
    print(f"  With data             : {with_data}")
    print(f"  Empty / failed        : {empty}")
    print(f"  Total candles fetched : {total_rows:,}")

    dated = stats.dropna(subset=["first_date"])
    if not dated.empty:
        print(f"  Date range (earliest) : {dated['first_date'].min().date()}")
        print(f"  Date range (latest)   : {dated['last_date'].max().date()}")
        latest_across = dated["last_date"].max()
        completeness = (dated["last_date"] >= latest_across).sum()
        print(f"  Latest data date     : {latest_across.date()}")
        print(f"  Up to latest         : {completeness}/{len(dated)}")

    print(f"\n  Top 5 by row count:")
    for _, r in stats.nlargest(5, "rows").iterrows():
        print(f"    {r['symbol']:20s}  {int(r['rows']):>8,} rows")

    print(f"\n  Bottom 5 by row count (with data):")
    for _, r in stats[stats["rows"] > 0].nsmallest(5, "rows").iterrows():
        print(f"    {r['symbol']:20s}  {int(r['rows']):>8,} rows")


if __name__ == "__main__":
    main()
