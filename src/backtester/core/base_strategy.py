from __future__ import annotations

from abc import ABC, abstractmethod

from nautilus_trader.model.data import Bar
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.trading.strategy import Strategy

from backtester.core.models import is_market_closing


class BaseConfig(StrategyConfig, frozen=True, kw_only=True):
    force_eod_close: bool


class BaseStrategy(Strategy, ABC):
    config: BaseConfig

    @property
    @abstractmethod
    def instrument_id(self) -> InstrumentId:
        ...

    def on_bar(self, bar: Bar) -> None:
        # ponytail: EOD exit lives here, not in every strategy
        if not self.portfolio.is_flat(self.instrument_id):
            if self.config.force_eod_close and is_market_closing(bar.ts_init):
                self.close_all_positions(
                    self.instrument_id, reduce_only=True, tags=["EOD"]
                )
                return
        self._handle_bar(bar)

    @abstractmethod
    def _handle_bar(self, bar: Bar) -> None:
        ...
