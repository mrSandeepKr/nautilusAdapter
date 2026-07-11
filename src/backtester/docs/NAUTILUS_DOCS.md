# Nautilus Trader — Verified API Reference

Do not re-research these. Verified against the installed package at `nautilus_trader==latest` (venv at repo root). All line references relative to `venv/lib/python3.14/site-packages/nautilus_trader/`.

---

## Data & Timestamps

### Bar Timestamp Rule (Look-Ahead Guard)

The engine advances the sim clock to `bar.ts_init` and executes `on_bar`-triggered orders at that nanosecond. Therefore **`ts_init` must be the bar close time** for no-look-ahead execution. `ts_event` is informational.

| Field | Convention | Engine usage |
|-------|-----------|--------------|
| `ts_event` | bar open time | used for sorting, informational |
| `ts_init` | bar CLOSE time | **clock advances to this**; orders submitted in `on_bar` settle here |

`DataEngineConfig.time_bars_timestamp_on_close` applies **only to internally aggregated bars** (`AggregationSource.INTERNAL`). For `EXTERNAL` bars (our case), it is irrelevant — the engine uses `ts_init` from the `Bar` object as-is.

### Bar Columns for Direct Construction

From `model/data.pyx:1510`:

```python
Bar(bar_type, open, high, low, close, volume, ts_event, ts_init)
```

All `open`/`high`/`low`/`close` are `Price` objects with correct `price_precision`. `volume` is `Quantity` with `size_precision` (Equity hardcodes `size_precision=0`).

Validation: `high >= open`, `high >= low`, `high >= close`, `low <= open`, `low <= close`. Raise if violated.

### Sort Order

`sort_data()` sorts by `ts_init`. `BacktestNode` does this automatically. When manually loading 200 instruments, load all with `sort=False` and call `sort_data()` once (verified performance optimization).

---

## Bar Execution

**File:** `backtest/engine.pyx:4847`

With `bar_execution=True` (default), the matching engine decomposes each bar into synthetic OHLC trade ticks and runs them through the matching engine so the market actually moves intra-bar. Trailing stops trail against these synthetic ticks.

### bar_adaptive_high_low_ordering

`config.py:172, engine.pyx:4863`

- `False` (default): fixed order **O → H → L → C**.
- `True`: if `High` is closer to `Open` than `Low` → O→H→L→C; else **O→L→H→C**.

**Why adopt:** A trailing SELL stop on a daily bar with fixed ordering always tests `High` before `Low` → systematic bias (stop triggers optimistically on the high first). Adaptive ordering mitigates this. Free realism win for trailing stops on daily bars. **Always set `True`.**

### Fill Behavior on Bars

- Market orders submitted in `on_bar` fill at the next bar's open (no look-ahead).
- Submitted market orders queue and settle within the same `ts_init` timestamp (the bar close). The engine drains command queues per timestamp.
- `STOP_MARKET`: if bar opens past trigger (gap) → fill at open; if bar moves through trigger intra-bar → fill at trigger price.
- `LIMIT` resting orders: probability `prob_fill_on_limit` of filling when market rests on price (default `1.0` = always fill).

---

## Instruments & Precision

### Equity

`model/instruments/equity.pyx:85`

```python
Equity(
    instrument_id=InstrumentId(symbol, venue),
    raw_symbol=symbol,
    currency=INR,
    price_precision=2,        # NSE paise
    price_increment=Price.from_str("0.05"),   # NSE minimum tick
    lot_size=Quantity.from_int(250),
    isin="INE002A01018",
    margin_init=Decimal("0.20"),   # 20% initial margin
    margin_maint=Decimal("0.12"),  # 12% maintenance margin
    maker_fee=Decimal(0),          # overridden by FeeModel
    taker_fee=Decimal(0),
    ts_event=0,
    ts_init=0,
)
```

**Hardcoded internals** (cannot override): `multiplier=1`, `size_increment=1`, `size_precision=0`.

### Currency

```python
from nautilus_trader.model.currencies import INR   # prebuilt constant
# or Currency.from_str("INR")
```

For known fiat codes, `from_str(code)` returns canonical. For unknown codes, defaults to precision 8.

### InstrumentId / BarType Strings

```python
InstrumentId.from_str("RELIANCE.NSE")                           # symbol.venue
BarType.from_str("RELIANCE.NSE-1-DAY-LAST-EXTERNAL")            # external bars
BarType.from_str("RELIANCE.NSE-1-DAY-LAST")                     # EXTERNAL is default
```

### Precision Helpers on Instrument

```python
price = instrument.make_price(105.50)          # → Price(105.50, precision=2)
qty   = instrument.make_qty(250)               # → Quantity(250, precision=0)
```

---

## Account Types & Margin

### OmsType

`model/enums.py:366`

- `NETTING = 1` — single position per instrument (use this).
- `HEDGING = 2` — separate position IDs per entry.

### AccountType

`model/enums.py:260`

- `CASH = 1` — no margin, no leverage.
- `MARGIN = 2` — margin + leverage (use this for intraday MIS).
- `BETTING = 3`.

### Leverage with MARGIN

- `BacktestVenueConfig.default_leverage` — auto-defaults to `Decimal(10)` for MARGIN, `Decimal(1)` for CASH. For NSE MIS set `5`.
- Per-instrument `leverages: dict[InstrumentId, Decimal]` override.

### base_currency

- `BacktestVenueConfig.base_currency: str | None = None`.
- `None` = multi-currency account (INR starting balance, INR instruments → works but PnL reported per-currency).
- Set `base_currency="INR"` for clean single-currency reporting. **Not auto-inferred** from `starting_balances`.

---

## Trading Sessions & EOD

**Critical missing feature for NSE intraday MIS backtest.**

- **No trading sessions, no calendar, no market hours.**
- `InstrumentCloseType.END_OF_SESSION = 1` exists in the enum but is **silently ignored** by the matching engine (engine.pyx:4829-4845 — only `CONTRACT_EXPIRED` is processed).
- `InstrumentStatus` with `MarketStatusAction.CLOSE` is **informational only** — the engine does not flatten positions, reject orders, or stop trading.
- `TimeInForce.DAY = 5` exists in the enum but the engine **has no DAY-TIF implementation** — such orders behave like GTC.
- Positions **roll overnight automatically**. There is no flatten.

**Solution: strategy-implemented EOD square-off.** In `on_bar`:
```python
if self.portfolio.is_net_long(instrument_id):
    self.close_all_positions(instrument_id, reduce_only=True, tags=["EOD_SQUARE_OFF"])
```

---

## Liquidation

`BacktestVenueConfig(liquidation_enabled=True, liquidation_trigger_ratio=1.0, liquidation_cancel_open_orders=True)` exists on the config object but is **silently dropped** on the Cython `BacktestEngine` used by `BacktestNode`.

- The Cython `add_venue()` (engine.pyx:502) does **not** accept these params.
- `node.py:388-420` calls `add_venue()` without passing them. The config is ignored.
- The **Rust** `nautilus_pyo3.BacktestEngine.add_venue()` DOES accept them, but `BacktestNode` uses the Cython engine.

Even if wired, liquidation fires **only on margin breach** (`equity ≤ maintenance × ratio`), not on EOD/time — it's a risk safety net, not a square-off mechanism.

**Verdict:** Do not rely on `liquidation_enabled`. Use strategy-side EOD square-off for intraday exit, and position-size discipline for margin safety.

---

## Fees & Fill Model

### FillModel

`backtest/models/fill.pyx:34`

```python
FillModel(
    prob_fill_on_limit=1.0,   # pct of limit orders that fill at crossed price
    prob_slippage=0.0,        # pct of aggressive fills that slip 1 tick
    random_seed=None,
)
```

Defaults are clean for market-entry strategies. Set `prob_slippage=0.0` is correct for our daily-bar market entries (slippage on bars is "gap" behavior, not tick-level slip).

Wired via `BacktestVenueConfig.fill_model: ImportableFillModelConfig`. Config shape: `{"fill_model_path": "...", "config_path": "...", "config": {}}`.

### FeeModel

`backtest/models/fee.pyx:32`

```python
class FeeModel:
    def get_commission(self, order, fill_qty, fill_px, instrument) -> Money:
```

**Returns `Money(commission_value, instrument.quote_currency)`.**

Built-in subclasses:

| Class | Logic |
|-------|-------|
| `MakerTakerFeeModel` | `notional × (maker_fee|taker_fee)` — fraction of notional, symmetric buy/sell |
| `FixedFeeModel(commission: Money)` | flat per order or per fill |
| `PerContractFeeModel(commission: Money)` | `commission × fill_qty` |

All wired via `ImportableFeeModelConfig` on venue.

### NSE Fee Stack (NOT Built-In)

NSE has multi-component charges. Built-in models cannot capture:

- STT: 0.025% **sell-side only** (intraday), 0.1% sell-side (delivery)
- Exchange: ~0.00345% of turnover
- SEBI: ₹10/crore (~0.0001% of turnover)
- Stamp duty: 0.003% buy-side (varies by state, Maharashtra default)
- GST: 18% on (brokerage + exchange + SEBI)
- Brokerage: ₹20/trade or 0.05% notional (discount broker)

**Solution:** Custom `FeeModel` subclass. `get_commission(self, order, fill_qty, fill_px, instrument)` receives the full `Order` object → can read `order.side` to apply STT only on SELL. Wired via `ImportableFeeModelConfig`.

#### Gotcha: FeeModelConfig Must Subclass NautilusConfig

A custom fee config class MUST inherit from `NautilusConfig` (a `msgspec.Struct`) with `frozen=True`. Plain classes or generic dataclasses crash with:
```
"expected a subclass of NautilusConfig"
```

All numeric fields must be typed `str`, not `Decimal` — msgspec parses the config dict values through JSON, so `Decimal` fields get serialised as strings and fail type coercion. Parse to `Decimal` at runtime inside `get_commission`:

```python
class NseFeeModelConfig(NautilusConfig, frozen=True):
    stt_rate_sell: str = "0.00025"
    ...
# in get_commission:
stt = notional * Decimal(cfg.stt_rate_sell)
```

---

## Trailing Stops

### Trailing Stop Market Order

`common/factories.pyx:940`

```python
order_factory.trailing_stop_market(
    instrument_id=...,
    order_side=OrderSide.SELL,       # SELL for long exit
    quantity=event.quantity,          # PositionOpened event has .quantity directly
    trailing_offset=Decimal("0.10"),  # in price or basis_points etc.
    trailing_offset_type=TrailingOffsetType.PRICE,
    trigger_type=TriggerType.DEFAULT,
    reduce_only=True,
    # emulation_trigger: OMIT entirely (defaults to NO_TRIGGER).
    # See below — DEFAULT crashes on LAST-only bars.
)
```

### emulation_trigger = DEFAULT vs NO_TRIGGER

**Verified crash on LAST bars.**

- `NO_TRIGGER` (or omitting `emulation_trigger` entirely, which defaults to `NO_TRIGGER`): order sent directly to the venue/backtest matching engine, which manages the trail natively against bar data. **This is what works** with LAST-only daily bars + `bar_execution=True`.
- `DEFAULT`: `OrderEmulator` (execution/emulator.pyx) subscribes quote/bar data and locally evaluates the trigger + trail. **Requires a BID/ASK book.** With LAST-only bars (no quote feed), the emulator crashes:
  ```
  "cannot process trailing stop, no BID or ASK price"
  ```

**Verdict: omit `emulation_trigger` entirely** (defaults to `NO_TRIGGER`) when using LAST-only bars. The exchange simulation handles trailing stops on bars natively via `bar_adaptive_high_low_ordering=True`, which decomposes each bar into synthetic OHLC ticks for the matching engine to trail against.

> **Note:** `emulation_trigger=DEFAULT` would be the realistic choice for live NSE/Upstox (broker-side emulation on live stream), but it is **incompatible with LAST-only backtest bars**. For backtesting, use `NO_TRIGGER` + `bar_adaptive_high_low_ordering=True`.

### Trailing Offset Semantics

`execution/trailing.pyx:308`

For a SELL (LONG exit): `trigger_price = bid - trailing_offset` (for `DEFAULT` trigger_type) or `last - trailing_offset` (for `LAST_PRICE`).

**Ratchet (high-water-mark) behavior** confirmed (trailing.pyx:85-94): the stop only ever moves UP, never down. It sits `offset` below the highest bid/last seen since activation. For BUY (short exit) the inverse holds: `ask + offset`, ratcheting DOWN.

### TrailingStopLimit Variant

`factories.pyx:1056`

Same shape plus `limit_offset: Decimal` and `post_only: bool`. Not needed for our setup.

---

## Indicators & Warmup

### ATR

`indicators/volatility.pyx:57`

```python
AverageTrueRange(period=14, ma_type=MovingAverageType.SIMPLE, use_previous=True, value_floor=0.0)
```

- `handle_bar(bar)` → updates from `bar.high`, `bar.low`, `bar.close`.
- `self.value` (double) → current ATR.
- `self.initialized` (bool) → True after `period` inputs.

### Registration + Warmup Pattern (Mandatory)

Engine does **NOT** auto-gate entries on indicator readiness. Follow the canonical `ema_cross.py` pattern:

```python
def on_start(self):
    self.instrument = self.cache.instrument(self.config.instrument_id)
    self.atr = AverageTrueRange(self.config.atr_period)
    self.register_indicator_for_bars(self.config.bar_type, self.atr)
    self.subscribe_bars(self.config.bar_type)   # bars are pre-loaded

def on_bar(self, bar):
    if not self.indicators_initialized():        # ⬅️ MUST gate
        return
    # ... signal logic ...
```

`self.indicators_initialized()` (actor.pyx:703) returns `True` only when ALL registered indicators have `initialized == True`.

#### Gotcha: on_start — Don't Call self.stop() on Missing Instrument

If `self.cache.instrument(id)` returns `None` (no historical data for that symbol), **log a warning and return** — do NOT call `self.stop()`. Calling `self.stop()` triggers `on_stop`, which tries to cancel orders on an uninitialised strategy (no instrument, no indicators), causing errors. Let the engine handle the strategy lifecycle:

```python
def on_start(self):
    self._instrument = self.cache.instrument(self._instrument_id)
    if self._instrument is None:
        self.log.warning(f"Instrument {self._instrument_id} not found, skipping")
        return
    # ... register indicators, subscribe bars ...
```

### RSI Value Range

`momentum.pyx`

`RelativeStrengthIndex.value` returns a **0–1** float — NOT the traditional 0–100. Confirmed at momentum.pyx:83: `self._rsi_max = 1`. The standard RSI formula would set `_rsi_max = 100`; Nautilus normalises to 0–1.

Thresholds in strategy code must use 0–1 values:

```python
# CORRECT — 0-1 scale (matches Nautilus):
self._prev_rsi <= 0.5 <= curr_rsi < 0.75   # RSI crossing above 50 (0.5)
prev_rsi < 0.30 and curr_rsi >= 0.30        # oversold crossover

# WRONG — treating as 0-100 scale:
prev_rsi <= 50 <= curr_rsi < 75   # never true (RSI caps at 1.0)
```

### Available Indicators

All in `indicators/`:

| Module | Classes |
|--------|---------|
| `volatility.pyx` | ATR, BollingerBands, DonchianChannel, KeltnerChannel, VHF, VolRatio |
| `momentum.pyx` | RSI, Stochastic, ROC, Williams, etc. |
| `trend.pyx` | **MovingAverageConvergenceDivergence (MACD)**, Ichimoku, DirectionalMovement (+DI/-DI, not ADX), ParabolicSAR, Swing, etc. |
| `averages.pyx` | SMA, EMA, WMA, HMA, etc. |
| `volume.pyx` | OBV, VWAP, Klinger, Pressure |
| `fuzzy_candlesticks.pyx` | FuzzyCandlesticks (fuzzy feature extraction, not classic pattern detection) |

**No built-in** candlestick pattern detector (engulfing, doji, hammer, etc.). Must implement manually.

#### MACD

Use `MovingAverageConvergenceDivergence(fast_period, slow_period)`. The `.value` property returns the MACD line (fast_ma - slow_ma). No signal line or histogram built-in; apply SMA/EMA to `.value` yourself if needed.

#### ADX

**NOT built-in.** Only `DirectionalMovement` which gives `.pos` (+DI) and `.neg` (-DI). Must compute ADX manually: `dx = 100 * abs(+DI - -DI) / (+DI + -DI)`, then smooth over 14 periods.

#### Supertrend

**NOT built-in.** Build from ATR: `basic = (high + low) / 2`, `lower = basic - atr_mult * atr.value`.

#### Moving Average Crossover

**NOT built-in as a single indicator.** Create two MAs (e.g., `ExponentialMovingAverage(9)` + `ExponentialMovingAverage(21)`) and compare `.value` yourself. Store previous values in `_store_indicator_state()` to detect crossovers.

---

## Position Sizing

### FixedRiskSizer

`risk/sizing.pyx`

```python
from nautilus_trader.risk.sizing import FixedRiskSizer

sizer = FixedRiskSizer(instrument)
qty = sizer.calculate(
    entry=Price,              # entry price
    stop_loss=Price,          # stop loss price
    equity=Money,             # account equity
    risk=Decimal,             # risk percentage (e.g. Decimal("0.01") for 1%)
    commission_rate=Decimal(0),
    exchange_rate=Decimal(1),
    hard_limit=Decimal | None = None,
    unit_batch_size=Decimal(1),  # ⬅️ lot size for batching
    units=1,
)
# Returns Quantity (position size)
```

**Use `unit_batch_size` for lot rounding.** Pass `unit_batch_size=Decimal(str(lot_size))` to batch the output to lot size. Never manually round quantities with `qty // lot_size * lot_size` — the sizer handles it.

---

## Orders & Contingencies

### OrderFactory Methods

`common/factories.pyx`

| Method | Line | Use case |
|--------|------|----------|
| `.market(...)` | 236 | immediate entry |
| `.limit(..., price, post_only=...)` | 312 | resting entry |
| `.stop_market(..., trigger_price, trigger_type=...)` | 417 | hard stop |
| `.stop_limit(...)` | 520 | |
| `.trailing_stop_market(...)` | 940 | our exit |
| `.bracket(entry_type=MARKET, tp_price, sl_trigger, ...)` | 1193 | entry + TP + SL in one list |

### Bracket + Trailing Stop Pattern

**Never submit two competing exit orders for the same position.** When using trailing exits:

- **Trailing exit methods** (`atr_trailing`, `keltner_trailing`, `chandelier`): Create bracket with `tp_price` only (omit `sl_trigger_price`). The trailing stop handles the stop-loss side.
- **Fixed RR exit**: Create bracket with both `tp_price` AND `sl_trigger_price`. No separate trailing stop.

```python
# Trailing exit — bracket has TP only, trailing stop added in on_position_opened
bracket = self.order_factory.bracket(
    instrument_id=self._instrument_id,
    order_side=order_side,
    quantity=qty,
    tp_price=tp_price,
    # sl_trigger_price OMITTED — trailing stop handles it
)

# Fixed RR — bracket has both TP and SL
bracket = self.order_factory.bracket(
    instrument_id=self._instrument_id,
    order_side=order_side,
    quantity=qty,
    tp_price=tp_price,
    sl_trigger_price=stop_price,
)
```

### ContingencyType

`model/enums.py:301`

| Value | Meaning |
|-------|---------|
| `NO_CONTINGENCY = 0` | |
| `OCO = 1` | One-Cancels-Other (TP and SL cancel each other) |
| `OTO = 2` | One-Triggers-Other (entry fill releases children) |
| `OUO = 3` | One-Updates-Other |

Used by `OrderFactory.bracket(...)` — `OTO` on the entry + `OCO` between TP and SL children. Works on bar data (contingency processing is in the matching engine, independent of data feed type).

### Submit Order vs Order List

```python
self.submit_order(order, position_id=...)          # single order
self.submit_order_list(order_list, position_id=...) # bracket etc.
```

`position_id` on trailing stop links it to the position. `submit_order` with `position_id` attaches the order as a child of that position for reduce/modify accounting.

#### Gotcha: PositionOpened Event Shape

`PositionOpened` has `.quantity` and `.position_id` **directly on the event**, NOT via `.position.quantity`. Accessing `event.position` raises `AttributeError`:

```python
# WRONG:
quantity = event.position.quantity   # AttributeError
# CORRECT:
quantity = event.quantity
position_id = event.position_id
```

#### Gotcha: cache.positions(instrument_id=...) — Keyword Only

`Cache.positions(venue=None, instrument_id=None, ...)` — the **first positional argument is `venue`**, not `instrument_id`. Always use the keyword:

```python
self.cache.positions(instrument_id=self._instrument_id)   # correct
self.cache.positions(self._instrument_id)                  # WRONG — treated as venue
```

### Position Lifecycle Methods

```python
# Check if flat
self.portfolio.is_flat(instrument_id)
self.portfolio.is_completely_flat()

# Close positions
self.close_position(position)                              # single position
self.close_all_positions(instrument_id, reduce_only=True)  # all positions for instrument

# Cancel orders
self.cancel_order(order)
self.cancel_all_orders(instrument_id)

# Market exit (iterative: cancel all + close all + wait)
self.market_exit()
```

---

## Catalog & BacktestNode

### ParquetDataCatalog

`persistence/catalog/parquet.py:141`

```python
catalog = ParquetDataCatalog(path=$DATA_DIR / "catalog")

catalog.write_data(list[Bar])        # → groups by bar_type, serializes itself
catalog.write_data(list[Instrument])  # → groups by instrument_id (Equity etc.)
```

`write_data` accepts plain `list[Bar]` of Nautilus model objects — it serializes to Arrow schema internally. No manual pyarrow Table needed.

Catalog must contain both `Bar` data AND `Instrument` metadata (Equity objects) for `BacktestNode` to load them (`node.py` loads instruments via `catalog.instruments(instrument_ids=...)`).

### BacktestNode

`backtest/node.py:97`

```python
node = BacktestNode(configs=[run_config_1, run_config_2])
results: list[BacktestResult] = node.run()
```

- **Fresh engine per run.** No manual reset/clear_data needed.
- Engines persist if `dispose_on_completion=False` (needed for post-run `create_tearsheet(engine, ...)`).
- Configs run in order passed; results returned same order.

### BacktestRunConfig

`backtest/config.py:399`

```python
BacktestRunConfig(
    venues=[BacktestVenueConfig(...)],
    data=[BacktestDataConfig(...)],
    engine=BacktestEngineConfig(...),
    start="...",            # backtest window start
    end="...",              # backtest window end
    chunk_size=None,        # None = all-in-memory
    dispose_on_completion=False,
    raise_exception=True,   # crash on error vs swallow
)
```

### BacktestDataConfig for Multi-Instrument Bar Loading

`config.py:195`

```python
BacktestDataConfig(
    catalog_path=...,
    data_cls="nautilus_trader.model.data:Bar",    # ⬅️ colon separator
    instrument_ids=[...200...],                    # list of InstrumentId strings
    bar_spec="1-DAY-LAST",                         # auto-builds bar_type as "{inst}-1-DAY-LAST-EXTERNAL"
    start_time=...,                                # data filter start
    end_time=...,                                  # data filter end
)
```

**`data_cls` uses `:` as the module:class separator** (not `.`). Resolved via `resolve_path()` in `common/config.py:78` using `rsplit(":", 1)`.

### ImportableStrategyConfig — Same `:` Separator

`trading/config.py:104`

```python
ImportableStrategyConfig(
    strategy_path="backtester.strategy:BullishEngulfingStrategy",  # colon!
    config_path="backtester.strategy:BullishEngulfingConfig",      # colon!
    config={
        "instrument_id_str": "RELIANCE.NSE",
        "bar_type_str": "RELIANCE.NSE-1-DAY-LAST-EXTERNAL",
        "trade_qty": 250,
        "order_id_tag": "BE000",
        ...
    },
)
```

Config values are JSON-serialized → decoded as the `StrategyConfig` class via msgspec. **Use string fields** (`instrument_id_str`, `bar_type_str`) and parse in `__init__` to avoid msgspec coupling. `StrategyConfig` inherits `order_id_tag: str | None = None` and `strategy_id: StrategyId | None = None` from `ActorConfig`.

#### Gotcha: StrategyConfig Subclass Needs kw_only=True

`StrategyConfig` inherits optional fields (`order_id_tag: str | None = None`, `strategy_id`, etc.) from `ActorConfig`. When you subclass and add **required** fields after these optional parent fields, msgspec raises a field-ordering error. Add `kw_only=True` to the class definition to force keyword-only construction:

```python
class MyConfig(StrategyConfig, frozen=True, kw_only=True):
    instrument_id_str: str        # required, after parent's optional fields
    trade_qty: int
    ...
```

#### Gotcha: `&` in instrument_id_str Crashes DuckDB

```
catalog.query(Bar, identifiers=["M&M.NSE-15-MINUTE-LAST-EXTERNAL"])
→ ParserError: Expected end of statement, found: & at Line:1, Column:20
```

`ParquetDataCatalog.query()` passes identifiers as SQL expressions to DuckDB. The `&` character in NSE symbols (`M&M`, `J&KBANK`, `GVT&D`) is treated as a SQL bitwise AND operator. Nautilus has no built-in SQL identifier sanitization — must be handled at the call site.

Workaround: try/except with fallback, or replace `&` with `_` in the identifier string (but then it won't match the stored data). The safest: skip the problematic instrument in queries and use a default value.

### BacktestResult

`backtest/results.py:19`

```python
result = engine.get_result()   # after run()
result.stats_pnls["INR"]       # → {"PnL (total)": ..., "WinRate": ..., "ProfitFactor": ..., ...}
result.stats_returns           # → {"SharpeRatio": ..., "SortinoRatio": ..., "ReturnsVolatility": ..., ...}
result.summary                 # → dict[str, str] of counts (orders, positions, events)
result.total_orders            # int
result.total_positions         # int
```

`stats_pnls` and `stats_returns` come from `portfolio.analyzer.get_performance_stats_*`. `MaxDrawdown` is **not registered by default** — must be registered via `portfolio.analyzer.register_statistic(MaxDrawdown())` before running.

On BacktestNode: access engine via `node._engines[run_config.id]` (private but works). Set `dispose_on_completion=False` to keep engines alive.

---

## Logging

### Config

`common/config.py:575`

```python
LoggingConfig(
    log_level="INFO",                          # stdout level
    log_level_file=None,                       # None = no file logging
    log_file_name=None,
    log_component_levels=None,                 # per-actor filter
    log_components_only=False,
    bypass_logging=False,
)
```

### At 200 Strategies × 100k Bars Scale

Per-bar `self.log.info(repr(bar))` → ~20M log lines → dominates wall-clock time. **DO NOT do this.** Always:

```python
BacktestEngineConfig(
    logging=LoggingConfig(
        log_level="WARNING",                   # quiet stdout
        log_level_file="INFO",                 # full detail to file
        log_file_name="backtest.log",
    ),
)
```

And in strategy, use `self.log.debug(...)` for per-bar info (won't print at WARNING).

### Per-Strategy Silencing

Set `log_events=False`, `log_commands=False` in `BuyllishEngulfingConfig` (inherited from `ActorConfig`) to suppress Nautilus's automatic event/command logs per strategy.

---

## Reporting & Tearsheets

### Tearsheet

`analysis/tearsheet.py:283`

```python
from nautilus_trader.analysis.tearsheet import create_tearsheet

create_tearsheet(
    engine=engine,
    output_path="tearsheet.html",
    title="Bullish Engulfing - Train",
    benchmark_returns=nifty_daily_returns,   # pd.Series, index=date, values=%change
    benchmark_name="Nifty 50",
)
```

- `output_path` ending `.html` → interactive Plotly (full equity curve, drawdown, monthly heatmap, returns distribution, rolling Sharpe).
- `benchmark_returns` → adds Beta, Alpha, InformationRatio, TrackingError, TreynorRatio to the tearsheet stats table, overlays on equity curve.

### ReportProvider

`analysis/reporter.py:26`

```python
ReportProvider.generate_positions_report(engine.cache.positions())     → pd.DataFrame
ReportProvider.generate_account_report(engine.portfolio.account(...))  → pd.DataFrame
ReportProvider.generate_orders_report(engine.cache.orders())           → pd.DataFrame
ReportProvider.generate_fills_report(...)                               → pd.DataFrame
```

All return `pd.DataFrame`. Use directly for CSV export / custom metrics.

### PortfolioAnalyzer Extra Stats

`MaxDrawdown` class exists (`core/nautilus_pyo3.pyi:10741`) but is **not registered by default** on the analyzer. Register before run:

```python
from nautilus_trader.core.nautilus_pyo3 import MaxDrawdown
engine.portfolio.analyzer.register_statistic(MaxDrawdown())
```

(On BacktestNode: access via `node._engines[run_id].portfolio.analyzer` before `run()`. Engines created during `node.build()`.)

---

## What Nautilus Does NOT Have

| Feature | Status | Paper if needed |
|---------|--------|-----------------|
| Candlestick pattern detector (engulfing, doji, etc.) | ❌ | Manual in `on_bar` |
| EOD session-close flatten / calendar | ❌ | Strategy-implemented |
| DAY TIF auto-cancel | ❌ | Stale enum value, no implementation |
| NSE-style multi-component fee (STT, SEBI, etc.) | ❌ | Custom FeeModel subclass |
| Universe selection / screening | ❌ | External (BhavcopyClient etc.) |
| Walk-forward / parameter sweep / grid search | ❌ | Manual `BacktestRunConfig` loop |
| Holiday / half-day calendar | ❌ | Manual date filtering |
| Order routing per venue availability | ⚠️ | Binary (on/off), no session-aware routing |
| `LiquidationEnabled` with BacktestNode (Cython) | ❌ dead | Use Rust engine or ignore |
| Native trailing stop (exchange-side, NSE) | ❌ doesn't exist in real NSE | Broker emulates client-side |
