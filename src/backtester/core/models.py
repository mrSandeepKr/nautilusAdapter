from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from collections.abc import Callable
from nautilus_trader.trading.config import ImportableStrategyConfig


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
    config_builder: Callable[[list[UniverseEntry], dict[str, float], str], list[ImportableStrategyConfig]]
