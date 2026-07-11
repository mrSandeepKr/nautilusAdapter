from __future__ import annotations

import argparse

from backtester.core import StrategySpec, build_universe_liquid
from backtester.core.runner import run_backtest
from backtester.strategy_composite import (
    EXIT_METHODS,
    COMPOSITE_ENTRIES,
    build_composite_configs_for_entry,
)
from utility.file_storage import FileStorage

STRATEGIES: dict[str, StrategySpec] = {}


def register(name: str, spec: StrategySpec) -> None:
    STRATEGIES[name] = spec


def _bootstrap() -> None:
    for entry in COMPOSITE_ENTRIES:
        for exit_ in EXIT_METHODS:
            name = f"{entry}__{exit_}"
            register(name, StrategySpec(
                strategy_path="backtester.strategy_composite:CompositeStrategy",
                config_path="backtester.strategy_composite:CompositeConfig",
                config_builder=lambda u, c, b, entry=entry, exit_=exit_: build_composite_configs_for_entry(
                    u, c, b, entry_name=entry, exit_method=exit_,
                ),
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

    entries, bench = build_universe_liquid(n=args.n)
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
