from __future__ import annotations

import sys
from datetime import date, datetime, timezone

import pandas as pd

from backtester.core import build_universe_top_volatile
from historical_data_fetcher import HistoricalDataProvider, HistoricalDataStore
from provider.upstox import UpstoxClient

_NS = 1_000_000_000
TOP_VOLATILE_N = 200


def main() -> None:
    print(f"[1/3] Computing top {TOP_VOLATILE_N} volatile stocks from NSE bhavcopy...")
    entries, _benchmark = build_universe_top_volatile(n=TOP_VOLATILE_N)
    print(f"       Resolved {len(entries)} instrument keys")

    print("\n[3/3] Fetching 5-minute candles (cached via Parquet)...")
    provider = HistoricalDataProvider(
        storage=HistoricalDataStore(),
        fetcher=UpstoxClient(),
    )

    from_date = "2022-01-01"
    to_date = date.today().isoformat()
    interval = "5minute"

    records: list[dict] = []
    for entry in entries:
        sym = entry.symbol
        inst_key = entry.upstox_key
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