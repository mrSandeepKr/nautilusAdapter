from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from collections.abc import Callable

import pandas as pd
from nautilus_trader.trading.config import ImportableStrategyConfig


class TradeStyle(StrEnum):
    INTRADAY = "intraday"
    SWING = "swing"


TRADE_STYLE_CONFIGS: dict[TradeStyle, dict] = {
    TradeStyle.INTRADAY: {
        "fee_config": "backtester.core.fees:NseIntradayFeeConfig",
        "default_leverage": 5,
    },
    TradeStyle.SWING: {
        "fee_config": "backtester.core.fees:NseSwingFeeConfig",
        "default_leverage": 1,
    },
}


def margin_init(trade_style: TradeStyle) -> Decimal:
    return Decimal("1.00") / Decimal(str(TRADE_STYLE_CONFIGS[trade_style]["default_leverage"]))


def is_market_closing(ts_init_ns: int) -> bool:
    """Check if the bar's close time (ts_init) is at or after market close (15:30 IST).
    Works for any bar interval — the last bar of the day always ends at/after 15:30."""
    dt = pd.Timestamp(ts_init_ns, unit='ns', tz='Asia/Kolkata')
    return dt.hour > 15 or (dt.hour == 15 and dt.minute >= 30)


@dataclass(frozen=True)
class UniverseEntry:
    symbol: str
    upstox_key: str
    instrument_id_str: str
    tick_size: Decimal
    lot_size: int
    isin: str | None


@dataclass(frozen=True)
class BenchmarkEntry:
    symbol: str
    upstox_key: str
    instrument_id_str: str


@dataclass(frozen=True)
class StrategySpec:
    strategy_path: str
    config_path: str
    config_builder: Callable[[list[UniverseEntry], dict[str, float], str, TradeStyle], list[ImportableStrategyConfig]]
