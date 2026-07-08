# AGENTS.md — backtester

Backtest layer that turns cached Upstox historical data + a Nautilus Trader
`Strategy` into a train/validate equity-curve report. Sits **on top of**
the existing fetcher/provider stack.

## Structure

```
src/backtester/
  __init__.py            — empty (package marker; keeps `import backtester` side-effect free)
  __main__.py            — CLI entry point: strategy registry + argparse (NOT core)
  core/                  — shared platform code (CONSTANT — never touch when adding strategies)
    __init__.py          — re-exports: StrategySpec, UniverseEntry, BenchmarkEntry, build_universe
    models.py            — frozen dataclasses: UniverseEntry, BenchmarkEntry, StrategySpec
    universe.py          — build_universe_top_volatile(), build_universe_from_symbols()
    data_loader.py       — build_catalog(), load_benchmark_returns()
    fees.py              — NseFeeModel + NseFeeModelConfig (STT/SEBI/GST/brokerage)
    runner.py            — run_backtest(), comparison, verdict (pure orchestration, no CLI)
  strategy_*.py          — one file per strategy: Config + Strategy + build_*_configs()
  docs/
    NAUTILUS_DOCS.md     — verified Nautilus API facts + gotchas (read when something breaks)
```

## Layering (the important part)

- **`core/` is constant.** Adding a strategy never touches `core/`. It owns
  the universe, catalog, fees model, and engine orchestration — shared
  infrastructure that all strategies run through.
- **`__main__.py` is the only wiring point.** It holds the registry
  (`STRATEGIES: dict[str, StrategySpec]`) and the argparse CLI. A new
  strategy = one new `strategy_*.py` file + one `register()` call here.
- **`__init__.py` stays empty.** The package must import without side
  effects (Nautilus strategies import from it). Never put registry code or
  CLI here — that runs on every import.
- **Strategies are thin leaves.** A strategy file only declares its
  `Config`, its `Strategy` subclass, and a `build_*_configs` factory. It
  pulls everything else (universe, bars, fees, runner) from `core/`.

## How to build a strategy

1. **Create `strategy_<name>.py`** with `<Name>Config(StrategyConfig,
   frozen=True, kw_only=True)` and `<Name>Strategy(Strategy)`. Export
   `build_<name>_configs(universe, close_prices) → list[ImportableStrategyConfig]`.
   Lean on `docs/NAUTILUS_DOCS.md` for the Nautilus API surface and its
   gotchas (timestamp swap, fees, trailing stops, `PositionOpened`,
   `cache.positions`, `on_start`, `kw_only`) — it is the source of truth
   for Nautilus behaviour, verified against the installed version.

2. **Register in `__main__.py`** — add a lazy import inside
   `_bootstrap()` and a `register()` call:
   ```python
   from backtester.strategy_<name> import build_<name>_configs
   register("<name>", StrategySpec(
       strategy_path="backtester.strategy_<name>:<Name>Strategy",
       config_path="backtester.strategy_<name>:<Name>Config",
       config_builder=build_<name>_configs,
   ))
   ```
   No edits to `core/` — ever.

3. **Run** `python -m backtester --strategy <name>`. Smoke test small
   (`--n 3`) before running the full universe (`--n 200`) and the validate
   split. The registry is keyed by the `--strategy` choice string.

## File roles

| File | Role | Touch when adding a strategy? |
|------|------|-------------------------------|
| `core/models.py` | Dataclasses: `UniverseEntry`, `BenchmarkEntry`, `StrategySpec` | No (CONSTANT) |
| `core/universe.py` | NSE equity universe (bhavcopy volatility → instrument map) | No (CONSTANT) |
| `core/data_loader.py` | Cached Nautilus-schema DataFrame → Equity + `list[Bar]` + catalog | No (CONSTANT) |
| `core/fees.py` | Custom `NseFeeModel` (STT/SEBI/GST/brokerage) | No (CONSTANT) |
| `core/runner.py` | `BacktestNode` orchestration, train/validate split, tearsheets, verdict | No (CONSTANT) |
| `__main__.py` | CLI entry point: strategy registry + argparse | **Yes** — add one `register()` call |
| `strategy_<name>.py` | A new strategy's `Config` + `Strategy` + `build_*_configs()` | **New file** |
| `docs/NAUTILUS_DOCS.md` | Nautilus API facts + gotchas (verified) | Reference only |

## Reuse rules (do not duplicate)

- Models: `from backtester.core import StrategySpec, UniverseEntry, BenchmarkEntry`
- Universe: `from backtester.core import build_universe_top_volatile, build_universe_from_symbols`
- Runner: `from backtester.core.runner import run_backtest`
- CLI: `python -m backtester --strategy <name>` (entry point is `__main__.py`, not core)
- Bhavcopy: `BhavcopyClient(BhavcopyDataFetcher()).top_volatile(...)`
- Symbol→key: `InstrumentStore().resolve(symbol)`, tick/lot via `store.search(symbol)`
- Bars: `HistoricalDataProvider(HistoricalDataStore(), UpstoxClient()).fetch_historical_data(...)`
- Settings: `AppSettings` / `get_app_settings()` from `src/settings.py`; `get_upstox_settings()` from `src/provider/upstox/settings.py`
- Frame helpers: `empty_nautilus_frame()` / `NAUTILUS_COLUMNS`
- Paths: `FileStorage("catalog")` / `FileStorage("backtest_results")` under `$DATA_DIR/`

## Where to find things

| Need | Look in |
|------|---------|
| Nautilus API gotchas (timestamp swap, fees, trailing stops, PositionOpened, cache.positions, on_start, kw_only) | `docs/NAUTILUS_DOCS.md` — each section has a "Gotcha" subsection |
| Reference strategy implementation (Config + Strategy + factory shape) | any existing `strategy_*.py` file |
| CLI flags and registry wiring | `__main__.py` |

## Coding conventions (project-wide)

- **No `Optional`** — `X | None` (PEP 604).
- **No comments/docstrings unless requested.**
- `src/` layout; new package under `src/backtester/` auto-discovered.
- Never read `.env` directly; never hardcode `DATA_DIR`.
- Never persist from a provider; providers stay thin.
- Frozen `dataclass`/`NautilusConfig` for all value types and configs.

## When something breaks

Reach for `docs/NAUTILUS_DOCS.md` first — it is the verified Nautilus
Trader API surface for this repo, with a "Gotcha" subsection on each
topic. If a strategy misbehaves, the cause is almost always one of the
documented gotchas, not the `core/` plumbing.