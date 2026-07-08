from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

from nautilus_trader.model.data import Bar, BarSpecification, BarType
from nautilus_trader.model.enums import AggregationSource, BarAggregation, PriceType
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Currency, Price, Quantity
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog

from backtester.core.models import UniverseEntry
from historical_data_fetcher.historical_data_provider import HistoricalDataProvider
from historical_data_fetcher.historical_data_store import HistoricalDataStore
from provider.upstox.client import UpstoxClient

_UNIT_TO_AGG: dict[str, BarAggregation] = {
    "minute": BarAggregation.MINUTE,
    "hour": BarAggregation.HOUR,
    "day": BarAggregation.DAY,
    "week": BarAggregation.WEEK,
    "month": BarAggregation.MONTH,
}

_INTERVAL_PATTERN = re.compile(r"(\d+)(minute|hour|day|week|month)")

def bar_spec_from_interval(interval: str) -> BarSpecification:
    m = _INTERVAL_PATTERN.fullmatch(interval)
    if not m:
        msg = f"Unrecognised interval: {interval!r}"
        raise ValueError(msg)
    step = int(m.group(1))
    agg = _UNIT_TO_AGG[m.group(2)]
    return BarSpecification(step, agg, PriceType.LAST)


def bar_spec_str(interval: str) -> str:
    bs = bar_spec_from_interval(interval)
    return f"{bs.step}-{BarAggregation(bs.aggregation).name}-{PriceType(bs.price_type).name}"

def build_catalog(
    universe: list[UniverseEntry],
    catalog_path: Path,
    t0: str,
    t1: str,
    interval: str,
) -> ParquetDataCatalog:
    if catalog_path.exists() and any(catalog_path.iterdir()):
        return ParquetDataCatalog(str(catalog_path))

    bar_spec = bar_spec_from_interval(interval)
    provider = HistoricalDataProvider(HistoricalDataStore(), UpstoxClient())

    bars_data: list[Bar] = []
    instruments: list = []

    for entry in universe:
        df = provider.fetch_historical_data(entry.upstox_key, interval, t0, t1)
        if df.empty:
            continue

        instrument_id = InstrumentId.from_str(entry.instrument_id_str)
        bar_type = BarType(
            instrument_id,
            bar_spec,
            AggregationSource.EXTERNAL,
        )

        equity = Equity(
            instrument_id,
            Symbol(entry.symbol),
            Currency.from_str("INR"),
            2,
            Price(entry.tick_size, 2),
            Quantity.from_int(entry.lot_size),
            0, 0,
            margin_init=Decimal("0.20"),
            margin_maint=Decimal("0.12"),
            isin=entry.isin,
        )
        instruments.append(equity)

        for row in df.itertuples():
            o_val = Price(row.open, 2)
            h_val = Price(row.high, 2)
            l_val = Price(row.low, 2)
            c_val = Price(row.close, 2)
            if float(l_val) > float(o_val):
                o_val = c_val
            if float(h_val) < float(o_val) or float(h_val) < float(c_val):
                h_val = Price(max(float(o_val), float(c_val)), 2)
            bars_data.append(Bar(
                bar_type,
                o_val,
                h_val,
                l_val,
                c_val,
                Quantity(row.volume, 0),
                int(row.ts_init),    # ts_event = open time (informational)
                int(row.ts_event),   # ts_init = close time (execution)
            ))

    catalog = ParquetDataCatalog(str(catalog_path))
    catalog.write_data(bars_data + instruments)
    return catalog
