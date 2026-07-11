# Strategy Research Campaign — July 2026

Systematic search for a profitable intraday strategy on the NSE small/mid-cap
universe (15-minute bars). Conducted via subagent-based batch testing.

## Hard rules

These are non-negotiable for campaign integrity:

### Rule 1: Sub-agents for all batch work

The main context stays clean. Every batch run, variant test, and data
inspection is delegated to a subagent. The main thread only:
- Writes code/files
- Launches subagents
- Reads final results

Subagents receive a self-contained prompt with exact commands and a required
report format. They return structured summaries — never raw logs.

### Rule 2: Validation is a single final step — never touched during development

The validation period (`t_split` to `t1`) is **explored exactly once**: at the
end, to measure the final chosen strategy. All development, debugging,
screening, parameter tuning, and selection happens exclusively on training
data. Rationale:

- Every peek at validation leaks future information into decisions
- If validation is used to pick a variant, it becomes training
- A strategy that wins on both train and validate is one you can trust

Concretely:
- `batch_test.py` always runs with `t1` set just past `t_split` so the
  validation window is tiny — just enough to keep the engine happy, not
  enough to read performance
- The CLI's `--t1` and `--t-split` are only set to full ranges for the
  final "validate the winner" run
- `batch_results.csv` contains only training metrics; validation columns
  exist but are empty

---

## Infrastructure built

| File | Purpose |
|------|---------|
| `strategy_composite.py` | Single parameterized `CompositeStrategy` + `CompositeConfig` dispatching across 23 entry signals (15 bullish, 8 bearish), 4 exit methods, configurable filters, short/long direction, optional EOD close. Multiple `build_*_configs()` factory functions. |
| `batch_test.py` | Sequential batch runner that slices the full variant matrix and runs each on training data. Accepts `start_idx end_idx n interval` CLI args for subagent parallelisation. Output: `data_fetched/backtest_results/batch_results.csv` |
| `core/universe.py` | `build_universe_liquid(n, min_trade_value=50M)` — uses bhavcopy `TtlTrfVal`, filters to NSE_EQ via `InstrumentStore.search_exact()`. Replaces earlier `top_volatile` which picked illiquid micro-caps. |
| `core/__init__.py` | Exports `build_universe_liquid` |

### Files modified

| File | Change |
|------|--------|
| `__main__.py` | Auto-registers all `COMPOSITE_ENTRIES × EXIT_METHODS` combinations (92) as `{entry}__{exit}` strategy names. |
| `core/runner.py` | `_last_close_prices()` wrapped in try/except for `&`-in-symbol DuckDB crash (M&M, J&KBANK, GVT&D). |
| `src/provider/upstox/instrument_store.py` | Added `search_exact()` — returns all segment entries for exact symbol (not truncated by FO options). |

---

## Subagent workflow

**This is the workflow. Follow it exactly for all future campaigns.**

### Principle

The main context is reserved for writing code, launching subagents, and
reading final results. Subagents do everything else: batch runs, data
inspection, debugging output analysis. Each subagent is stateless — it
receives a self-contained prompt and returns a structured report.

### Prompt template (exact)

```
Run the batch test for strategy variants on training data (ONLY):

cd /Users/sandeepkumar/Documents/Projects/Tradings/nautilus && \
python src/backtester/batch_test.py {start} {end} {n_inst} {interval}

Never use --t1 or --t-split in batch scripts — batch_test.py
hardcodes training-only dates internally.

Wait for completion. Report:
1. Whether it completed (exit code)
2. Per-variant output: PnL%, Win Rate, # Trades, Profit Factor
3. TOP 10 variants sorted by training PnL%
4. Full CSV content (first 30 lines + last 10 lines)
5. List of any variants that produced zero trades
```

### Subagent contract

| Input | Source |
|-------|--------|
| Slice range | `{start} {end}` (indices into the 60+ variant list) |
| Universe size | `{n_inst}` — keep at 10 for screening, 50+ for confirmation |
| Interval | `{interval}` — normally `15minute` |
| Training data | Hardcoded in `batch_test.py` as `t0=2024-07-01`, `t1=2025-10-01`, `t_split=2025-09-27` |
| Validation | Tiny window (4 days) — exists only to keep engine alive, NEVER read for decisions |

### Output format (what subagent returns to main thread)

```
Completed: exit code 0

Per-variant:
  variant_1: PnL=X% WR=Y% T=Z PF=W time=Ts
  variant_2: PnL=X% WR=Y% T=Z PF=W time=Ts
  ...

Top 10 by PnL%:
  1. variant_a: X%
  2. variant_b: Y%
  ...

Zero-trade variants: [none / list]

CSV preview:
  (header + first 5 rows + last 5 rows)
```

### Batch matrix used in this campaign

| Batch | Subagent | Slice | Variants | Runtime |
|-------|----------|-------|----------|---------|
| A | ses_... | 0-20 | bullish_engulfing, morning_star, ema_crossover, rsi_oversold, volume_spike | ~25 min |
| B | ses_... | 20-40 | donchian_breakout, supertrend, vwap_bounce, macd_crossover, adx_trend | ~20 min |
| C | ses_... | 40-60 | rsi_macd_confluence, bollinger_squeeze, hammer_reversal, piercing_pattern, three_soldiers, bearish_engulfing, shooting_star, three_black_crows, death_cross, rsi_overbought | ~25 min |

---

## Entry signals tested (20)

### Bullish (long)

| Signal | Description | Status |
|--------|-------------|--------|
| `bullish_engulfing` | Red candle → green candle engulfing body | Works |
| `morning_star` | 3-candle: bearish, indecision, bullish | Fixed (prev_bar bug) |
| `ema_crossover` | EMA9 crosses above EMA21 | Fixed |
| `rsi_oversold` | RSI(14) < 30 then crosses above | Works |
| `volume_spike` | Close > SMA20 AND volume > 2× SMA | Works |
| `donchian_breakout` | Close > 20-period high | Never fires (15-min small caps) |
| `supertrend` | ATR-based trend filter proxy | Works |
| `vwap_bounce` | Price pulls back below VWAP then recovers | Fixed |
| `macd_crossover` | MACD > 0 (custom impl, nautilus MACD broken) | Works |
| `adx_trend` | ADX > 25 AND +DI > -DI | Fixed (nautilus DM.value always 0) |
| `rsi_macd_confluence` | RSI > 50 AND MACD > 0 | Works |
| `bollinger_squeeze` | BandWidth contraction + breakout | Works |
| `hammer_reversal` | Long lower wick + confirmation | Works |
| `piercing_pattern` | 2-candle: bearish, bullish closes above 50% | Works |
| `three_soldiers` | 3 consecutive strong green candles | Fixed |

### Bearish (short)

| Signal | Description | Status |
|--------|-------------|--------|
| `bearish_engulfing` | Green candle → red candle engulfing body | Best performer |
| `shooting_star` | Long upper wick, small body | Works |
| `three_black_crows` | 3 consecutive strong red candles | Works |
| `death_cross` | EMA9 crosses below EMA21 | Works |
| `rsi_overbought` | RSI > 70 then crosses below | Works |
| `dark_cloud_cover` | 2-candle: bullish, bearish opens above high closes below 50% | Trades (86 on 75k bars) but underperforms |
| `bearish_harami` | 2-candle: bullish, bearish body inside prev body | Trades (58) but underperforms |
| `evening_star` | 3-candle: bullish, indecision, bearish | 0 trades on 15min (too rare) |

### Exit methods

| Method | Description |
|--------|-------------|
| `fixed_risk_reward` | Bracket: TP at entry ± RR×risk, SL at stop price |
| `atr_trailing` | Trailing stop at highest/lowest + ATR×mult |
| `keltner_trailing` | Trail at Keltner channel midline |
| `chandelier` | Trail at 22-period extreme − 3×ATR |

---

## Nautilus indicator bugs encountered

| Indicator | Bug | Workaround |
|-----------|-----|------------|
| `MovingAverageConvergenceDivergence(12,26,9)` | Internal EMAs are `None`; crashes on `update_raw` in nautilus 1.230.0 | Replace with `EMA12 - EMA26` calculation |
| `DirectionalMovement(14)` | `.value` always returns 0.0 (line 251-348 of `.pyx` never assigns `self.value`) | Compute ADX manually from `pos`/`neg` buffered + smoothed via SMA(14) |

---

## Full results matrix

Test conditions: 10 instruments, 15-minute, 2024-07-01–2025-09-27 train,
2025-09-27–2025-10-01 validate (tiny val window for screening).

```
Variant                                              Trades(T/V)    TrPnL%       ValPnL%     TrWR    ValWR   TrPF   ValPF
———————————————————————————————————————————————————   ————————————   ———————————  ——————————  —————   —————   —————  —————
bearish_engulfing + vol_filt (liquid 10)              1142/701      +196.62%     -22.85%     47.1%   42.4%   1.47   0.90
bearish_engulfing + 3:1 RR (liquid 10)                1477/863       +99.55%     -48.09%     42.2%   38.4%   1.23   0.80
bearish_engulfing + no_filt (liquid 10)                1495/870       +74.54%     -42.02%     44.7%   41.0%   1.20   0.81
three_black_crows + fixed_rr (liquid 10)               2436/1406     +322.01%     -42.79%     48.5%   44.5%   1.42   0.88
bearish_engulfing + vol+rsi (liquid 10)                 266/152       +22.55%      -8.82%     45.5%   38.2%   1.22   0.88
bearish_engulfing + rsi_filt (liquid 10)                358/200       +18.27%      -9.94%     44.1%   38.5%   1.15   0.90
bear_engulf + atr_trail (liquid 10)                    1505/869       +11.11%     -56.78%     43.1%   38.6%   1.07   0.70
bullish_engulfing (top_vol n=200, original)              506/383     -77.68%     -59.83%     26.5%   32.4%   0.36   0.43
```

## Campaign v2: Liquid universe — July 2026

### Changes from v1

| Change | Rationale |
|--------|-----------|
| `build_universe_liquid(n, min_trade_value=50M)` replaces `top_volatile()` | v1 universe was micro-caps with ~₹10M daily trade value |
| Resolves only `NSE_EQ` segment via `search_exact()` | Avoids `NSE_FO` (options) and `BSE_EQ` symbols |
| Catalog incremental fetch in `build_catalog()` | Only fetches missing instruments; won't re-fetch existing |
| 3 new bearish signals | `dark_cloud_cover`, `bearish_harami`, `evening_star` (all trade but underperform) |
| Batch slicing fix | `chunk = variants[start_idx:end_idx]` enables parallel subagents |

### Batch screen results (v2)

92 variants × 10 liquid stocks (top 10 by TtlTrfVal), 3 parallel subagents.

```
Variant                          Trades  TrPnL%    TrWR   TrPF
———————————————————————————————  ——————  ————————  —————  —————
three_black_crows + fixed_rr      398     +16.64%   42.7%  1.14
rsi_oversold + fixed_rr           150      +7.90%   50.0%  1.80
bearish_engulfing + fixed_rr      178      +5.69%   39.3%  1.14
shooting_star + fixed_rr           72      +5.21%   47.2%  1.17
bullish_engulfing + fixed_rr      208      +4.56%   38.5%  1.12
```

### Validation: DENIED

- Winner: `three_black_crows__fixed_risk_reward`
- Universe: 200 liquid stocks (189 with data)
- Training PnL: -100.12% (42.7% WR, 1.02 PF, 10318 trades)
- Validation PnL: -99.99% (42.1% WR, 0.57 PF, 6795 trades)
- Strategy works on top-10 mega-caps but collapses at scale — does not generalize.

### DuckDB `&`-in-symbol crash

NSE symbols `M&M`, `J&KBANK`, `GVT&D` cause DuckDB SQL parse errors in
`ParquetDataCatalog.query()` — `&` is treated as a SQL operator. Fixed by
try/except in `_last_close_prices()` with fallback to default close price.

### Variants with zero trades (screening phase)

These produced no signals on 10 instruments over 14 months of 15-minute data.
Most were fixed after debugging:

| Variant | Root cause | Fixed? |
|---------|-----------|--------|
| `morning_star` | `_prev_bar` set before signal dispatch, so bar references were shifted by 1 | ✅ |
| `ema_crossover` | Same `_prev_bar` timing bug | ✅ |
| `donchian_breakout` | `close > dc.upper` never triggers on 15-min small caps (inherently strict) | ❌ Design |
| `vwap_bounce` | `_prev_bar` timing bug | ✅ |
| `adx_trend` | `DirectionalMovement.value` permanently 0 in nautilus 1.230.0 | ✅ |
| `three_soldiers` | `_prev_bar` timing bug | ✅ |

### Effect of universe on performance

| Universe | Variant | Train PnL% | Val PnL% |
|----------|---------|-----------|---------|
| liquid 10 (hand-picked) | bearish_engulfing + vol | +196.62% | -22.85% |
| top_volatile n=10 | bearish_engulfing + vol | -65.91% | — |
| top_volatile n=50 | bearish_engulfing | -68.87% | -81.40% |

The "liquid 10" universe was manually selected based on available 15-minute
data. The apparent outperformance on that set is in-sample selection bias.
Moving to the automated `top_volatile` universe collapses all gains.

---

## Key findings

1. **No strategy generalises.** Every variant profitable on training data
   reverses in the validation period. The market regime changed: training
   favoured short selling on small caps (strong bearish trends), validation
   punished it.

2. **Universe quality dominates signal quality.** "Top volatile" stocks from
   bhavcopy are illiquid small-caps unsuitable for systematic trading.
   Changing from a hand-picked liquid set to the automated volatile screen
   flipped +196% to -69%.

3. **Short selling outperforms long** across all entry signals on this
   universe during this training window. `bearish_engulfing` was the best
   entry, `fixed_risk_reward` the best exit.

4. **More trades ≠ worse.** The `bearish_engulfing + vol_filt` variant had
   fewer trades than `no_filt` (+196% vs +74%) — filtering improved both
   PnL and stability. But `three_black_crows` had the most trades and the
   highest train PnL (+322%), suggesting the pattern itself is predictive,
   not the count.

5. **EOD forced close damages RR ratio.** The 15:15 IST square-off converts
   potentially winning trades into marginal winners/losses. AvgWinner and
   AvgLoser were nearly equal despite a 2:1 configured RR ratio.

6. **Nautilus 1.230.0 indicator bugs** affect `MovingAverageConvergenceDivergence`
   and `DirectionalMovement.value`. Workarounds are in `strategy_composite.py`.

---

## Next steps (recommended)

### Priority 1: Better universe
Current `BhavcopyClient.top_volatile()` returns a volatility-sorted list that
includes micro-caps, penny stocks, and suspended companies. Replace with a
liquidity/market-cap filter:

- Use `InstrumentStore.search()` to filter by `segment="NSE_EQ"` and
  `lot_size=1` (liquid derivatives-eligible stocks)
- Fetch Nifty 500 constituent list from NSE website
- Use bhavcopy `TtlTrfVal` (total trade value) instead of volatility for
  ranking

### Priority 2: Regime adaptation
Add a market-state filter: only take long signals when Nifty 50 > SMA200,
only take short signals when Nifty 50 < SMA200. This prevents fighting the
broader trend.

### Priority 3: Remove EOD forced close
The `force_eod_close=False` option already exists in `CompositeConfig` (added
during this campaign). Run the best short variant with it enabled, allowing
trades to run overnight until TP/SL is hit.

### Priority 4: Per-stock selection
Some stocks performed consistently across train AND validation (AARTECH,
DBEIL, NIITLTD). Build a stock-ranking model that selects only instruments
where the strategy historically works.

### Priority 5: 1-day timeframe
Piercing pattern on 1-day data produced zero signals on 10 instruments over
14 months. Try with the full 200-instrument universe or relax the pattern
recognition to allow partial pierces (closes above 25% instead of 50%).

### Priority 6: Statistical arbitrage
Instead of directionally betting on individual stocks, trade the spread
between the best and worst performers (long-short portfolio). This is
market-neutral and less sensitive to regime changes.

---

## How to run a new campaign

### Training phase (all work happens here)

```bash
# Step 1: Add/modify signals in strategy_composite.py
#         (__main__.py auto-registers all variants)

# Step 2: Quick smoke test — 3 instruments, 1 variant, tiny training slice
python -m backtester \
  --strategy bearish_engulfing__fixed_risk_reward \
  --n 3 --interval 15minute \
  --t0 2024-07-01 --t1 2025-01-01 --t-split 2024-12-01

# Step 3: Batch screen — launch 3 subagents in parallel,
#          each running 20 variants on 10 instruments
#          (validation window is tiny, NEVER read it)
subagent: python src/backtester/batch_test.py 0 20 10 15minute
subagent: python src/backtester/batch_test.py 20 40 10 15minute
subagent: python src/backtester/batch_test.py 40 60 10 15minute

# Step 4: Read batch_results.csv from main thread.
#          Pick the best variant by TRAINING PnL only.
#          Do not look at validation columns.

# Step 5: (Optional) Run the winner with larger universe,
#          still on training data only
python -m backtester \
  --strategy bearish_engulfing__fixed_risk_reward \
  --n 50 --interval 15minute \
  --t0 2024-07-01 --t1 2025-10-01 --t-split 2025-09-27
```

### Validation phase (exactly once, at the very end)

```bash
# Only after the winning variant is frozen:
python -m backtester \
  --strategy bearish_engulfing__fixed_risk_reward \
  --n 200 --interval 15minute \
  --t0 2024-07-01 --t1 2026-07-07 --t-split 2025-09-27
```

**If validation PnL is negative: do not iterate.** Go back to training, design
a new signal or universe, and repeat. Every validation run burns objectivity
— you get one honest measurement per campaign.

### Adding a new entry signal

1. Add the variant name to `COMPOSITE_ENTRIES` in `strategy_composite.py`
2. If bearish, also add to `SHORT_SIGNALS`
3. Implement `_signal_<name>(self, prev: Bar, bar: Bar) -> bool`
4. Add it to the dispatch dict inside `_detect_entry()` (or `_detect_entry_short()`)
5. If it's a multi-bar pattern, manage `self._signal_candle` and `self._pending_stop_low`/`_pending_stop_high`
6. Deploy via `_gen_composite_entries()` — it picks up `COMPOSITE_ENTRIES` and `EXIT_METHODS` automatically
