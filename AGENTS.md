# AGENTS.md

## Project

Provider-agnostic historical data fetcher normalised to Nautilus Trader backtest Parquet schema.
Not an end state — active development, structure will evolve.

## Setup

```bash
./setup_venv.sh   # creates venv, pip install -e ., playwright install chromium
```

Or use `direnv` (`.envrc` sources venv + sets `PYTHONPYCACHEPREFIX`).
Python 3.14+ required (per `pyproject.toml`).

## Architecture

```
src/
  settings.py                    — AppSettings (DATA_DIR from .env)
  historical_data_fetcher/       — core orchestration
    interfaces.py                — HistoricalDataFetcher Protocol
    historical_data_provider.py  — cache-or-fetch, owns data transformation
    historical_data_store.py     — Parquet I/O over FileStorage
  provider/
    realtime_http_client.py      — generic two-tier rate-limited HTTP client
    upstox/                      — Upstox broker: auth, instruments, fetch
    screener/                    — NSE bhavcopy + index constituents
  utility/
    file_storage.py              — flat-file key-value store under DATA_DIR
    nautilus_utility.py          — empty_nautilus_frame(), NAUTILUS_COLUMNS
```

Key design:
- `HistoricalDataFetcher` Protocol — providers implement this; must NOT persist to disk
- `HistoricalDataProvider` owns the cache-or-fetch decision + data transformation
- `HistoricalDataStore` is pure Parquet I/O (no transformation)
- `RealtimeHttpClient` enforces per-second + per-minute rate limits transparently
- `UpstoxAuthenticator` uses Playwright (headless Chromium) for OAuth2 + TOTP login
- All settings from `.env` via `pydantic-settings` (two tiers: `AppSettings`, `UpstoxSettings`)

## Data layout

```
$DATA_DIR/
  historical_data/<instrument>/<from_date>_<to_date>_<interval>.parquet
  bhavcopy/<date>.parquet
  instrument_cache/<exchange>.json.gz
```

## Commands

No test/lint/typecheck tooling set up yet (no pytest config, no ruff, no mypy).
If adding one, match the `src/` layout and `pyproject.toml` build config.

## Coding conventions

- **`.env` is functional** — contains `DATA_DIR` + all Upstox credentials. Never modify or rewrite it; the existing values are correct.
- **Leverage existing functions** — reuse helpers from `utility/`, `settings.py`, `HistoricalDataStore`, etc. Don't duplicate logic (e.g. use `empty_nautilus_frame()`, `FileStorage`, `AppSettings`/`get_upstox_settings()`).
- **Separation of concern** — `HistoricalDataStore` does Parquet I/O only; `HistoricalDataProvider` orchestrates cache-or-fetch; providers implement `HistoricalDataFetcher` Protocol and must NOT persist to disk. Keep layers distinct.
- **No `Optional` types** — use bare `| None` union syntax (PEP 604). Avoid `Optional[...]`, avoid `typing.Optional`.

Other conventions:
* Uses `src/` layout with `[tool.setuptools.packages.find] where = ["src"]`
* Parquet data columns: `ts_event`, `ts_init`, `open`, `high`, `low`, `close`, `volume` (all PyArrow dtypes)
* Times stored as nanosecond uint64 timestamps
* `.env` is at repo root, gitignored; must set `DATA_DIR` at minimum
* Upstox interval strings: `1minute`, `3minute`, `5minute`, `15minute`, `30minute`, `1hour`, `1day`, `1week`, `1month`
* `InstrumentStore.resolve("RELIANCE")` returns `"NSE_EQ|INE002A01018"` — used as the `instrument` key for historical fetch
* Indices use `"NSE_INDEX|..."` keys (e.g. `"NSE_INDEX|Nifty 50"`)
* Access token cached at `$DATA_DIR/upstox_access_token.txt` (auto-refreshed if <1h to expiry)
* Upstox rate limits enforced at: 8 req/s, 450 req/min
