from __future__ import annotations

import argparse

from backtester.core import StrategySpec, build_universe_liquid, build_universe_nifty50, build_universe_top_volatile
from backtester.core.models import TradeStyle
from backtester.core.runner import run_backtest
from backtester.strategy_composite import (
    EXIT_METHODS,
    COMPOSITE_ENTRIES,
    build_composite_configs_for_entry,
)
from backtester.strategy_swing import build_swing_configs
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
                config_builder=lambda u, c, b, ts, entry=entry, exit_=exit_: build_composite_configs_for_entry(
                    u, c, b, entry_name=entry, exit_method=exit_, trade_style=ts,
                ),
            ))

    register("swing", StrategySpec(
        strategy_path="backtester.strategy_swing:SwingStrategy",
        config_path="backtester.strategy_swing:SwingConfig",
        config_builder=build_swing_configs,
    ))


def _build_universe(name: str, n: int, window: int) -> tuple:
    if name == "nifty50":
        return build_universe_nifty50()
    if name == "volatile":
        return build_universe_top_volatile(n=n, window=window)
    return build_universe_liquid(n=n)


def main() -> None:
    _bootstrap()

    parser = argparse.ArgumentParser(description="Run backtest")
    parser.add_argument("--strategy", required=True, choices=sorted(STRATEGIES))
    parser.add_argument("--universe", choices=["liquid", "nifty50", "volatile"], default="liquid")
    parser.add_argument("--n", type=int, default=200)
    parser.add_argument("--window", type=int, default=20)
    parser.add_argument("--interval", default="1day")
    parser.add_argument("--total-corpus", default="1000000 INR")
    parser.add_argument("--t0", default="2024-07-01")
    parser.add_argument("--t1", default="2026-07-07")
    parser.add_argument("--t-split", default="2025-09-27")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--trade-style", type=TradeStyle, choices=list(TradeStyle), default=TradeStyle.SWING)
    args = parser.parse_args()

    # Intraday only makes sense on intraday intervals; on day/week/month bars
    # is_market_closing() fires on every bar (ts_init == 15:30 close), forcing
    # an immediate EOD square-off and degenerating the backtest.
    if args.trade_style is TradeStyle.INTRADAY and not args.interval.endswith(("minute", "hour")):
        parser.error(f"--trade-style intraday requires a minute/hour interval, got {args.interval!r}")

    entries, bench = _build_universe(args.universe, args.n, args.window)
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
        trade_style=args.trade_style,
    )


if __name__ == "__main__":
    main()
