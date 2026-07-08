from __future__ import annotations

from pathlib import Path

from nautilus_trader.backtest.config import (
    BacktestDataConfig,
    BacktestEngineConfig,
    BacktestRunConfig,
    BacktestVenueConfig,
    DataEngineConfig,
    ImportableFeeModelConfig,
)
from nautilus_trader.backtest.node import BacktestNode
from nautilus_trader.common.config import LoggingConfig
from nautilus_trader.model.data import Bar
from nautilus_trader.trading.config import ImportableStrategyConfig

from backtester.core.benchmark import build_benchmark, load_benchmark_returns
from backtester.core.data_loader import bar_spec_str, build_catalog
from backtester.core.models import BenchmarkEntry, StrategySpec, UniverseEntry
from backtester.core.report_maker import make_report

_DATA_CLS = "nautilus_trader.model.data:Bar"
_FEE_MODEL_PATH = "backtester.core.fees:NseFeeModel"
_FEE_CONFIG_PATH = "backtester.core.fees:NseFeeModelConfig"


def _build_run_config(
    catalog_path: Path,
    universe: list[UniverseEntry],
    strategy_configs: list[ImportableStrategyConfig],
    t_start: str,
    t_end: str,
    log_file_name: str,
    bar_spec: str,
    total_corpus: str,
) -> BacktestRunConfig:
    return BacktestRunConfig(
        venues=[BacktestVenueConfig(
            name="NSE",
            oms_type="NETTING",
            account_type="MARGIN",
            base_currency="INR",
            starting_balances=[total_corpus],
            default_leverage=5,
            bar_execution=True,
            bar_adaptive_high_low_ordering=True,
            fee_model=ImportableFeeModelConfig(
                fee_model_path=_FEE_MODEL_PATH,
                config_path=_FEE_CONFIG_PATH,
                config={},
            ),
        )],
        data=[BacktestDataConfig(
            catalog_path=str(catalog_path),
            data_cls=_DATA_CLS,
            instrument_ids=[e.instrument_id_str for e in universe],
            bar_spec=bar_spec,
            start_time=t_start,
            end_time=t_end,
        )],
        engine=BacktestEngineConfig(
            strategies=strategy_configs,
            logging=LoggingConfig(
                log_level="WARNING",
                log_level_file="INFO",
                log_file_name=log_file_name,
            ),
            data_engine=DataEngineConfig(validate_data_sequence=True),
        ),
        start=t_start,
        end=t_end,
        dispose_on_completion=False,
        raise_exception=True,
    )


def _last_close_prices(
    catalog,
    universe: list[UniverseEntry],
    bar_spec: str,
) -> dict[str, float]:
    prices: dict[str, float] = {}
    for e in universe:
        bars = catalog.query(
            Bar,
            identifiers=[f"{e.instrument_id_str}-{bar_spec}-EXTERNAL"],
        )
        if bars:
            prices[e.symbol] = float(bars[-1].close.as_double())
        else:
            prices[e.symbol] = 100.0
    return prices


def run_backtest(
    universe: list[UniverseEntry],
    benchmark: BenchmarkEntry,
    t0: str,
    t1: str,
    t_split: str,
    spec: StrategySpec,
    interval: str,
    total_corpus: str,
    catalog_path: Path,
    output_dir: Path,
) -> dict[str, tuple[str, str]]:

    catalog = build_catalog(universe, catalog_path, t0, t1, interval)
    build_benchmark(catalog, benchmark, interval, t0, t1)
    bs = bar_spec_str(interval)
    close_prices = _last_close_prices(catalog, universe, bs)
    strategy_configs = spec.config_builder(universe, close_prices, bs)

    train_run = _build_run_config(
        catalog_path, universe, strategy_configs, t0, t_split, "train.log", bs, total_corpus,
    )
    validate_run = _build_run_config(
        catalog_path, universe, strategy_configs, t_split, t1, "validate.log", bs, total_corpus,
    )

    node = BacktestNode(configs=[train_run, validate_run])
    results = node.run()
    engines = node.get_engines()

    nifty_ret = load_benchmark_returns(catalog, benchmark)

    comparison = make_report(
        engines[0], engines[1], results[0], results[1], nifty_ret, output_dir
    )

    return comparison
