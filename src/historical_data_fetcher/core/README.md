# Core Interface — Adopter Responsibilities

`historical_data_fetcher.core.interfaces.HistoricalDataFetcher` defines the
public Protocol every provider must implement. Beyond producing rows, each
adopter **strictly owns the parsing and normalization** of its provider's
API responses into Nautilus Trader's backtest-ready Parquet schema.

## Nautilus Bar Schema

A provider *must* persist a DataFrame whose columns and dtypes match the
following exactly. Nautilus Trader's Parquet catalog reader depends on these
types to ingest bars without coercion.

| Column     | dtype    | Description                                            |
|------------|----------|--------------------------------------------------------|
| `ts_event` | `uint64[pyarrow]` | Nanoseconds since UNIX epoch — **close time** of bar.  |
| `ts_init`  | `uint64[pyarrow]` | Nanoseconds since UNIX epoch — **open time** of bar.  |
| `open`     | `float64[pyarrow]`| Open price.                                            |
| `high`     | `float64[pyarrow]`| High price.                                            |
| `low`      | `float64[pyarrow]`| Low price.                                             |
| `close`    | `float64[pyarrow]`| Close price.                                           |
| `volume`   | `uint64[pyarrow]` | Traded volume.                                         |

Rows must be sorted by `ts_init` ascending with no duplicates.

## Adopter Checklist

1. Implement `fetch_historical_data(instrument, interval, from_date, to_date)`.
2. Translate provider-specific interval strings to the provider's API parameters.
3. Parse the provider's timestamp format into UTC nanoseconds (`ts_init`).
4. Compute `ts_event` as `ts_init + bar duration in nanoseconds`.
5. Cast OHLC to `float64[pyarrow]` and `volume` to `uint64[pyarrow]`; cast both timestamps to `uint64[pyarrow]`.
6. Save under `config.DATA_DIR` as `.parquet` and return the resulting file path.