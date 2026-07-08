from __future__ import annotations

from decimal import Decimal

import pandas as pd
from nautilus_trader.indicators import AverageTrueRange, RelativeStrengthIndex, SimpleMovingAverage, VolumeWeightedAveragePrice
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TrailingOffsetType, TriggerType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price
from nautilus_trader.risk.sizing import FixedRiskSizer
from nautilus_trader.trading.config import ImportableStrategyConfig, StrategyConfig
from nautilus_trader.trading.strategy import Strategy

from backtester.core.models import UniverseEntry


def build_bullish_engulfing_configs(
    universe: list[UniverseEntry],
    _close_prices: dict[str, float],
    bar_spec: str,
) -> list[ImportableStrategyConfig]:
    configs: list[ImportableStrategyConfig] = []
    for i, entry in enumerate(universe):
        configs.append(ImportableStrategyConfig(
            strategy_path="backtester.strategy_bullish_engulfing:BullishEngulfingStrategy",
            config_path="backtester.strategy_bullish_engulfing:BullishEngulfingConfig",
            config={
                "instrument_id_str": entry.instrument_id_str,
                "bar_type_str": f"{entry.instrument_id_str}-{bar_spec}-EXTERNAL",
                "risk_percent": "0.01",
                "atr_period": 14,
                "atr_mult": 2.0,
                "order_id_tag": f"BE{i:03d}",
                "log_events": False,
                "log_commands": False,
            },
        ))
    return configs


class BullishEngulfingConfig(StrategyConfig, frozen=True, kw_only=True):
    instrument_id_str: str
    bar_type_str: str
    risk_percent: str
    atr_period: int
    atr_mult: float
    order_id_tag: str


class BullishEngulfingStrategy(Strategy):

    def __init__(self, config: BullishEngulfingConfig) -> None:
        super().__init__(config)
        self._instrument_id = InstrumentId.from_str(config.instrument_id_str)
        self._bar_type = BarType.from_str(config.bar_type_str)
        self._instrument = None
        self._sizer = None
        self.atr = None
        self.sma20 = None
        self.rsi = None
        self.vwap = None
        self._prev_rsi = None
        self._prev_bar = None

    def on_start(self) -> None:
        self._instrument = self.cache.instrument(self._instrument_id)
        if self._instrument is None:
            self.log.warning(f"Instrument {self._instrument_id} not found, skipping")
            return
        self._sizer = FixedRiskSizer(self._instrument)
        self.atr = AverageTrueRange(self.config.atr_period)
        self.sma20 = SimpleMovingAverage(20)
        self.rsi = RelativeStrengthIndex(14)
        self.vwap = VolumeWeightedAveragePrice()
        self.register_indicator_for_bars(self._bar_type, self.atr)
        self.register_indicator_for_bars(self._bar_type, self.sma20)
        self.register_indicator_for_bars(self._bar_type, self.rsi)
        self.register_indicator_for_bars(self._bar_type, self.vwap)
        self.subscribe_bars(self._bar_type)

    def _atr_offset(self) -> Decimal:
        return Decimal(str(round(
            self.atr.value * self.config.atr_mult,
            self._instrument.price_precision,
        )))

    def on_bar(self, bar: Bar) -> None:
        if self._instrument is None or not self.indicators_initialized():
            return

        if not self.portfolio.is_flat(self._instrument_id):
            self._exit_position(bar)
            return

        prev = self._prev_bar
        self._prev_bar = bar
        if prev is None:
            return

        if self._should_enter_position(prev, bar):
            self._enter_position(bar)

        self._prev_rsi = self.rsi.value

    def on_position_opened(self, event) -> None:
        if self._instrument is None or self.atr is None:
            return
        self._set_trailing_stop(event)

    def on_stop(self) -> None:
        self.cancel_all_orders(self._instrument_id)

    # --- helpers ---

    def _should_enter_position(self, prev: Bar, bar: Bar) -> bool:
        if self._bar_type.spec.timedelta < pd.Timedelta(days=1):
            dt = pd.Timestamp(bar.ts_event, unit='ns', tz='Asia/Kolkata')
            if dt.hour < 10:
                return False

        if bar.close.as_double() <= self.sma20.value or bar.close.as_double() < self.vwap.value:
            return False

        curr_rsi = self.rsi.value
        if self._prev_rsi is None or not (self._prev_rsi <= 0.5 <= curr_rsi < 0.75):
            return False

        if bar.volume.as_double() <= prev.volume.as_double():
            return False

        return (prev.close < prev.open
            and bar.close > bar.open
            and bar.open <= prev.close
            and bar.close > prev.open)

    def _enter_position(self, bar: Bar) -> None:
        account = self.portfolio.account(venue=self._instrument_id.venue)
        equity = account.balance_total(account.base_currency)
        risk = Decimal(self.config.risk_percent)
        atr_offset = self._atr_offset()
        stop_price = Price(
            bar.close.as_double() - float(atr_offset),
            self._instrument.price_precision,
        )
        raw_qty = int(self._sizer.calculate(
            entry=bar.close,
            stop_loss=stop_price,
            equity=equity,
            risk=risk,
        ).as_double())
        lot_size = int(self._instrument.lot_size.as_double())
        qty = self._instrument.make_qty(max(lot_size, (raw_qty // lot_size) * lot_size))
        if qty.as_double() <= 0:
            return
        order = self.order_factory.market(
            self._instrument_id,
            OrderSide.BUY,
            qty,
        )
        self.submit_order(order)

    def _exit_position(self, bar: Bar) -> None:
        self.close_all_positions(
            self._instrument_id,
            reduce_only=True,
            tags=["EOD_SQUARE_OFF"],
        )
        self._prev_bar = bar

    def _set_trailing_stop(self, event) -> None:
        offset = self._atr_offset()
        trailing = self.order_factory.trailing_stop_market(
            instrument_id=self._instrument_id,
            order_side=OrderSide.SELL,
            quantity=event.quantity,
            trailing_offset=offset,
            trailing_offset_type=TrailingOffsetType.PRICE,
            trigger_type=TriggerType.DEFAULT,
            reduce_only=True,
        )
        self.submit_order(trailing, position_id=event.position_id)
