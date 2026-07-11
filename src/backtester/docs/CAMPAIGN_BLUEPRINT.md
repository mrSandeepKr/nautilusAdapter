# Campaign Blueprint — AI-to-AI Handoff

This document teaches the next AI how to run a strategy research campaign.
Follow exactly. Do not improvise.

---

## Hard Rules

### Rule 1: Sub-agents do all batch work

The main context only:
- Writes/edits code
- Launches subagents
- Reads final results

Every batch run, data inspection, or debugging session goes to a subagent.
Subagents receive a self-contained prompt with exact commands. They return
structured summaries — never raw logs.

### Rule 2: Validation is explored exactly once — at the end

The validation period (`t_split` to `t1`) is NEVER:
- Used to pick a variant
- Used to tune parameters
- Inspected during development

All screening, debugging, and selection happens on training data only.
`batch_test.py` hardcodes a tiny validation window (4 days) — just enough
to keep the engine running, not enough to read performance.

When validation is finally run: if PnL is negative, do NOT iterate. Go back
to training, design something new, restart the campaign. Every validation
run burns objectivity — one honest measurement per campaign.

---

## Worktree setup (reproducibility + isolation)

Before any campaign work, create a detached worktree. This pins the code to
a known commit so results are reproducible, and frees the main worktree for
concurrent development.

```bash
# 1. Commit all campaign code first (required — worktree uses HEAD,
#    unstaged changes are not included)
git add -A && git commit -m "campaign: <descriptive message>"

# 2. Create a detached worktree at this commit
#    This pins the code: results are reproducible even if main branch moves
DATE=$(date +%Y%m%d)
git worktree add --detach ../nautilus-campaign-$DATE HEAD

# 3. Run ALL campaign commands from the worktree
cd ../nautilus-campaign-$DATE

# Main worktree (nautilus/) is now free for concurrent development
```

The main worktree (`nautilus/`) is now free to modify, switch branches, etc.
while the campaign runs in isolation.

**When campaign finishes:**
```bash
# 4. Clean up the worktree
git worktree remove ../nautilus-campaign-$DATE
```

---

## Execution flow

### Phase 1: Instrument universe

1. Default: `build_universe_liquid(n, min_trade_value=50_000_000)` in `core/universe.py`
   - Uses `BhavcopyClient.latest_bhavcopy()` → filters `TtlTrfVal >= min_trade_value`
   - Resolves only `NSE_EQ` segment via `InstrumentStore.search_exact(symbol)`
   - Rejects `EQ`, `BE`, `BZ` series from the universe
   - Import: `from backtester.core import build_universe_liquid`
2. Previous default `BhavcopyClient.top_volatile(N)` is **deprecated** — it picks
   illiquid micro-caps unsuitable for systematic intraday trading
3. If universe quality is suspect, launch a subagent to inspect (check bhavcopy
   TtlTrfVal distribution via `BhavcopyClient.latest_bhavcopy().data`)

### Phase 2: Add entry signals

File: `src/backtester/strategy_composite.py`

1. Add variant name to `COMPOSITE_ENTRIES`
2. If bearish, also add to `SHORT_SIGNALS`
3. Implement `_signal_<name>(self, prev: Bar, bar: Bar) -> bool`
4. Add it to the dispatch dict inside `_detect_entry()` or `_detect_entry_short()`
5. If it's a multi-bar pattern, manage `self._signal_candle` and
   `self._pending_stop_low` / `_pending_stop_high`

Signals are registered automatically by `__main__.py` via `_gen_composite_entries()`.
Each variant becomes `{name}__{exit_method}` — no manual wiring needed.

### Phase 3: Smoke test

```bash
cd <worktree>
python -m backtester \
  --strategy bearish_engulfing__fixed_risk_reward \
  --n 3 --interval 15minute \
  --t0 2024-07-01 --t1 2025-01-01 --t-split 2024-12-01
```

If it crashes: fix in main worktree, recommit, recreate worktree.

### Phase 4: Batch screen (training only)

Launch 3 subagents in parallel, each running ~20 variants:

```
Subagent A: python src/backtester/batch_test.py 0 20 10 15minute
Subagent B: python src/backtester/batch_test.py 20 40 10 15minute
Subagent C: python src/backtester/batch_test.py 40 60 10 15minute
```

Each subagent reports: per-variant PnL%, WR, trades, PF, top 10 sorted by
training PnL%, and any zero-trade variants.

### Phase 5: Select winner by training PnL only

Read `data_fetched/backtest_results/batch_results.csv` from the main thread.
Pick the variant with the highest training PnL%.
Do NOT look at validation columns.

### Phase 6: Validate exactly once

Only after the winner is frozen:

```bash
python -m backtester \
  --strategy <winner> \
  --n 200 --interval 15minute \
  --t0 2024-07-01 --t1 2026-07-07 --t-split 2025-09-27
```

If validation PnL is negative: record the result, do not iterate.
Return to Phase 2 with a new signal idea.

---

## Subagent prompt template (copy-paste)

```
You are a batch test subagent. Run the backtest and return a structured report.

cd <worktree_path> && python src/backtester/batch_test.py {start} {end} {n} {interval}

Wait for completion. Return exactly:

1. Exit code (0 = success)
2. Per-variant table:
   variant | PnL% | WR% | Trades | PF | Runtime
3. Top 10 by PnL%
4. Zero-trade variants (if any) with suspected cause
5. First 30 + last 10 lines of the CSV

NO extra commentary. NO analysis. Just the report.
```

---

## Error recovery

### Zero trades

| Possible Cause | Check | Fix |
|---|---|---|
| `_prev_bar` timing | Signal uses `prev_bar` but `on_bar` sets `self._prev_bar = bar` before dispatch | Reorder: dispatch first, then assign |
| Nautilus indicator bug | `MovingAverageConvergenceDivergence` crashes | Replace with `EMA12 - EMA26` |
| Nautilus indicator bug | `DirectionalMovement.value` always 0 | Compute ADX from `pos`/`neg` + SMA14 |
| Pattern too strict | `donchian_breakout` close > dc.upper | Relax threshold or accept as design limit |
| No data | Instrument has no bars in range | Check `data_fetched/` for parquet files |

### Crashes on startup

| Symptom | Cause | Fix |
|---|---|---|
| `KeyError` on strategy name | Variant not in registry | Run `python -m backtester --help` to list registered names |
| `NoneType` on indicator | Nautilus internal bug | Implement workaround in strategy code |
| ImportError | Missing module | Check `src/` layout and `pyproject.toml` |
| DuckDB SQL parse error on `&` | NSE symbols `M&M`, `J&KBANK`, `GVT&D` contain `&` — treated as SQL operator | try/except in `_last_close_prices()` with 100.0 fallback |

### Validation collapses

If train is +200% and val is -20%:
- Most likely cause: universe selection bias (hand-picked stocks)
- Fix: switch to rules-based universe (bhavcopy liquid ranking)
- If that still fails: market regime shift (try regime filter)

---

## File reference

| File | Role |
|---|---|
| `src/backtester/strategy_composite.py` | All entry signals, exit methods, variant configs. Edit this to add/modify strategies. |
| `src/backtester/__main__.py` | CLI entry point. Auto-registers all variants — usually no edits needed. |
| `src/backtester/batch_test.py` | Batch runner for subagent parallelisation. Training dates hardcoded inside. |
| `src/backtester/core/runner.py` | Orchestrator. Keep unchanged during campaigns. |
| `src/backtester/docs/STRATEGY_RESEARCH_2026.md` | Historical record of the July 2026 campaign. Read for reference. |
| `src/backtester/docs/CAMPAIGN_BLUEPRINT.md` | This file — instructions for the next AI. |
| `.env` | Contains DATA_DIR + Upstox creds. Never modify. |
| `src/backtester/core/universe.py` | `build_universe_liquid()` — bhavcopy-liquidity-ranked universe. Default for campaigns. |
| `src/provider/upstox/instrument_store.py` | `search_exact()` — returns all segment entries for exact symbol. |
| `data_fetched/backtest_results/batch_results.csv` | Consolidated output from batch screen. |
| `data_fetched/historical_data/` | Cached parquet files. Append-only. |

## Known nautilus 1.230.0 bugs

| What | Workaround |
|---|---|
| `MovingAverageConvergenceDivergence(12,26,9)` — internal EMAs are `None` | Use `EMA(12).value - EMA(26).value` instead |
| `DirectionalMovement(14).value` — always returns 0.0 | Compute ADX manually: buffer `pos`/`neg`, smooth via SMA(14) |
| `OrderSide.SELL_SHORT` — does not exist | Use `OrderSide.SELL` with NETTING account type |

## Constants

| Parameter | Value |
|---|---|
| Training range | `2024-07-01` to `2025-09-27` |
| Validation split | `2025-09-27` |
| Full data range | `2024-07-01` to `2026-07-07` |
| Batch universe size | 10 instruments |
| Validation universe size | 200 instruments |
| Interval | `15minute` |
| Upstox intervals | `1minute`, `3minute`, `5minute`, `15minute`, `30minute`, `1hour`, `1day`, `1week`, `1month` |
