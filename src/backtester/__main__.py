from __future__ import annotations

import argparse

from backtester.core import StrategySpec, build_universe_top_volatile
from backtester.core.runner import run_backtest
from utility.file_storage import FileStorage

STRATEGIES: dict[str, StrategySpec] = {}


def register(name: str, spec: StrategySpec) -> None:
    STRATEGIES[name] = spec


def _bootstrap() -> None:
    from backtester.strategy_bullish_engulfing import build_bullish_engulfing_configs
    register("bullish-engulfing", StrategySpec(
        strategy_path="backtester.strategy_bullish_engulfing:BullishEngulfingStrategy",
        config_path="backtester.strategy_bullish_engulfing:BullishEngulfingConfig",
        config_builder=build_bullish_engulfing_configs,
    ))


def main() -> None:
    _bootstrap()

    parser = argparse.ArgumentParser(description="Run backtest")
    parser.add_argument("--strategy", required=True, choices=sorted(STRATEGIES))
    parser.add_argument("--n", type=int, default=200)
    parser.add_argument("--window", type=int, default=20)
    parser.add_argument("--interval", default="1day")
    parser.add_argument("--total-corpus", default="1000000 INR")
    parser.add_argument("--t0", default="2024-07-01")
    parser.add_argument("--t1", default="2026-07-07")
    parser.add_argument("--t-split", default="2025-09-27")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    entries, bench = build_universe_top_volatile(n=args.n, window=args.window)
    run_backtest(
        universe=entries,
        benchmark=bench,
        t0=args.t0,
        t1=args.t1,
        t_split=args.t_split,
        spec=STRATEGIES[args.strategy],
        interval=args.interval,
        total_corpus=args.total_corpus,
        catalog_path=FileStorage("catalog").root / args.interval,
        output_dir=FileStorage("backtest_results").root,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
