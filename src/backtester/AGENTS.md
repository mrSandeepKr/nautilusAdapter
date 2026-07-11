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
  strategy_composite.py  — COMPOSITE entry-signal sweep (see "Composite vs isolated" below)
  strategy_*.py          — ISOLATED strategies: one file per strategy with its own Config + Strategy + build_*_configs()
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
- **Composite vs isolated.** Two strategies-live patterns coexist by design:

  - **`strategy_composite.py` — composite (non-isolated batch sweeps).** A single
    `CompositeStrategy` class dispatches to many entry-signal `_signal_<name>`
    methods × `EXIT_METHODS` exit stacks via string dispatch, all registered
    together as `COMPOSITE_ENTRIES × EXIT_METHODS` (currently 23 × 4 = 92
    `"<entry>__<exit>"` CLI keys in `_bootstrap()`). Use it when a new entry
    signal reuses the existing indicator/filter/time-gating/stop plumbing of the
    composite class — i.e. you're scanning a grid of similar signals where each
    is just another candlestick-pattern or indicator-trigger routine. **Do not
    create an isolated file per signal here; that defeats the shared
    edge-indicator plumbing the composite exists to amortise.**

  - **`strategy_<name>.py` — isolated (one file per standalone strategy).** Use
    when a strategy has bespoke per-bar logic, bespoke indicators, a different
    lifecycle, custom exit semantics, or otherwise would bleed into other
    signals if bolted onto the composite. Register it with **one** explicit
    `register("<name>", ...)` call in `_bootstrap()` (see "How to build an
    isolated strategy" below).

## How to add a strategy — composite or isolated?

**Pick the composite** (`strategy_composite.py`) when the new entry signal
fits the existing shared indicator/filter/time-gating/stop contract of the
composite class — i.e. it is a non-isolated case where you'll want a
Cartesian entry × exit sweep against the existing 92-strategy grid.

To extend the composite:

1. **Add a `_signal_<name>(self, prev, bar) -> bool`** (or `_signal_<name>(self,
   bars: list[Bar | None]) -> bool` for 3-bar patterns) method to
   `CompositeStrategy`. Put longs in `_detect_entry`'s dispatch dict, shorts
   in `_detect_entry_short`'s dict.
2. **Append the name to `COMPOSITE_ENTRIES`** (and to `SHORT_SIGNALS` if it's
   a short signal — the two must overlap exactly on shorts, hand-maintained).
3. Done. `_bootstrap()` already iterates `COMPOSITE_ENTRIES × EXIT_METHODS`,
   so `<name>__<exit>` CLI keys appear automatically. **No** `register()`
   call, **no** new file, **no** `_bootstrap()` edit. Do not isolate signals
   that share the composite's plumbing into separate files — that's the case
   the composite exists for.

**Pick isolated** (`strategy_<name>.py`) when the strategy cannot be expressed
as another `_signal_*` row in the composite — bespoke indicators, bespoke
lifecycle, custom exit semantics, or per-variant config the composite
`CompositeConfig` cannot express. See "How to build an isolated strategy"
below.

## How to build an isolated strategy

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
| `__main__.py` | CLI entry point: strategy registry + argparse | **Only for isolated strategies** — add one `register()` call (composite is auto-registered via `COMPOSITE_ENTRIES × EXIT_METHODS`) |
| `strategy_composite.py` | `CompositeStrategy` + `CompositeConfig` + 23 `_signal_*` methods × 4 `EXIT_METHODS`; produces all `"<entry>__<exit>"` keys | **Edit** when extending the composite sweep (add method + entry name; `_bootstrap()` picks it up automatically) |
| `strategy_<name>.py` | An isolated strategy's `Config` + `Strategy` + `build_*_configs()` | **New file** — only for strategies that don't fit the composite contract |
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
| Composite signal plumbing (shared indicators, `_signal_*` shape, `_detect_entry`/`_detect_entry_short` dispatch, `CompositeConfig` fields, `EXIT_METHODS`) | `strategy_composite.py` |
| Reference shape for an *isolated* strategy (Config + Strategy + factory, no string dispatch) | a future `strategy_<name>.py` (no current examples — all entries live in the composite) |
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