from __future__ import annotations

from decimal import Decimal

import pandas as pd
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import AggregationSource
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import IndexInstrument
from nautilus_trader.model.objects import Currency, Price, Quantity
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog

from backtester.core.data_loader import bar_spec_from_interval
from backtester.core.models import BenchmarkEntry
from historical_data_fetcher.historical_data_provider import HistoricalDataProvider
from historical_data_fetcher.historical_data_store import HistoricalDataStore
from provider.upstox.client import UpstoxClient


def build_benchmark(
    catalog: ParquetDataCatalog,
    benchmark: BenchmarkEntry,
    interval: str,
    t0: str,
    t1: str,
) -> None:
    bars = catalog.query(Bar, identifiers=[benchmark.instrument_id_str])
    if bars:
        return

    bar_spec = bar_spec_from_interval(interval)
    provider = HistoricalDataProvider(HistoricalDataStore(), UpstoxClient())
    df = provider.fetch_historical_data(benchmark.upstox_key, interval, t0, t1)
    if df.empty:
        return

    bench_id = InstrumentId.from_str(benchmark.instrument_id_str)
    bench_bar_type = BarType(
        bench_id,
        bar_spec,
        AggregationSource.EXTERNAL,
    )
    instruments = [
        IndexInstrument(
            bench_id,
            Symbol(benchmark.symbol),
            Currency.from_str("INR"),
            2,
            0,
            Price.from_str("0.05"),
            Quantity.from_int(1),
            0, 0,
        ),
    ]
    bars_data = [
        Bar(
            bench_bar_type,
            Price(row.open, 2),
            Price(row.high, 2),
            Price(row.low, 2),
            Price(row.close, 2),
            Quantity(row.volume, 0),
            int(row.ts_init),
            int(row.ts_event),
        )
        for row in df.itertuples()
    ]
    catalog.write_data(bars_data + instruments)


def load_benchmark_returns(
    catalog: ParquetDataCatalog,
    benchmark: BenchmarkEntry,
) -> pd.Series:
    bars = catalog.query(Bar, identifiers=[benchmark.instrument_id_str])
    if not bars:
        return pd.Series(dtype="float64")
    closes = pd.Series(
        [float(b.close.as_double()) for b in bars],
        index=pd.to_datetime([b.ts_init for b in bars], unit="ns"),
    )
    closes = closes.sort_index()
    return closes.pct_change().dropna()
