from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

from backtester.core import build_universe_liquid
from backtester.core.runner import run_backtest
from backtester.core.models import StrategySpec
from utility.file_storage import FileStorage

from backtester.strategy_composite import COMPOSITE_ENTRIES, EXIT_METHODS
from backtester.strategy_composite import build_composite_configs_for_entry


def run_one_variant(
    name: str,
    entry: str,
    exit_: str,
    n: int,
    interval: str,
    t0: str,
    t1: str,
    t_split: str,
    total_corpus: str,
) -> dict:
    entries, bench = build_universe_liquid(n=n)
    if not entries:
        return {"variant": name, "error": "empty universe"}

    spec = StrategySpec(
        strategy_path="backtester.strategy_composite:CompositeStrategy",
        config_path="backtester.strategy_composite:CompositeConfig",
        config_builder=lambda u, c, b: build_composite_configs_for_entry(
            u, c, b, entry_name=entry, exit_method=exit_,
        ),
    )

    try:
        comparison = run_backtest(
            universe=entries,
            benchmark=bench,
            t0=t0,
            t1=t1,
            t_split=t_split,
            spec=spec,
            interval=interval,
            total_corpus=total_corpus,
            catalog_path=FileStorage("catalog").root / interval,
            output_dir=FileStorage("backtest_results").root,
        )

        return {
            "variant": name,
            "train_pnl_pct": comparison["Total PnL%"][0],
            "train_win_rate": comparison["Win Rate"][0],
            "train_trades": comparison["# Trades"][0],
            "train_profit_factor": comparison["Profit Factor"][0],
            "train_avg_winner": comparison["AvgWinner"][0],
            "train_avg_loser": comparison["AvgLoser"][0],
            "train_expectancy": comparison["Expectancy (₹)"][0],
        }
    except Exception as e:
        return {"variant": name, "error": str(e)}


def main() -> None:
    variants: list[tuple[str, str, str]] = []
    for entry in COMPOSITE_ENTRIES:
        for exit_ in EXIT_METHODS:
            variants.append((f"{entry}__{exit_}", entry, exit_))

    args = sys.argv[1:]
    if len(args) >= 4:
        start_idx = int(args[0])
        end_idx = int(args[1])
        n = int(args[2])
        interval = args[3]
    elif len(args) >= 2:
        n = int(args[0])
        interval = args[1]
        start_idx = 0
        end_idx = len(variants)
    elif len(args) >= 1:
        n = int(args[0])
        interval = "15minute"
        start_idx = 0
        end_idx = len(variants)
    else:
        n = 10
        interval = "15minute"
        start_idx = 0
        end_idx = len(variants)
    chunk = variants[start_idx:end_idx]

    # single train period (t0/t1 cover training, t_split near end for small validate)
    t0 = "2024-07-01"
    t1 = "2025-10-01"
    t_split = "2025-09-27"

    out = FileStorage("backtest_results").root / "batch_results.csv"
    results: list[dict] = []
    total = len(chunk)
    for i, (name, entry, exit_) in enumerate(chunk):
        print(f"\n[{i + 1}/{total}] {name}")
        t0r = time.time()
        row = run_one_variant(name, entry, exit_, n, interval, t0, t1, t_split, "1000000 INR")
        elapsed = time.time() - t0r
        row["elapsed_s"] = round(elapsed, 1)
        results.append(row)

        pnl = row.get("train_pnl_pct", "ERR")
        wr = row.get("train_win_rate", "ERR")
        pf = row.get("train_profit_factor", "ERR")
        print(f"  → PnL%={pnl} WR={wr} PF={pf} ({elapsed:.0f}s)")
        _append_csv(out, results)

    _append_csv(out, results)
    print(f"\nDone. Results at {out}")


def _append_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
