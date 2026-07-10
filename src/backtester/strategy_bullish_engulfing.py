from __future__ import annotations

from decimal import Decimal

import pandas as pd
from nautilus_trader.indicators import AverageTrueRange, RelativeStrengthIndex, SimpleMovingAverage, VolumeWeightedAveragePrice
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, OrderType, TrailingOffsetType, TriggerType
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
        self.volume_sma = None
        self._prev_rsi = None
        self._prev_bar = None
        self._engulfing_prev = None
        self._engulfing_bar = None

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
        self.volume_sma = SimpleMovingAverage(10)
        self.register_indicator_for_bars(self._bar_type, self.atr)
        self.register_indicator_for_bars(self._bar_type, self.sma20)
        self.register_indicator_for_bars(self._bar_type, self.rsi)
        self.register_indicator_for_bars(self._bar_type, self.vwap)
        self.register_indicator_for_bars(self._bar_type, self.volume_sma)
        self.subscribe_bars(self._bar_type)

    def _atr_offset(self) -> Decimal:
        return Decimal(str(round(
            self.atr.value * self.config.atr_mult,
            self._instrument.price_precision,
        )))

    def _is_market_closing(self, bar: Bar) -> bool:
        dt = pd.Timestamp(bar.ts_event, unit='ns', tz='Asia/Kolkata')
        return dt.hour >= 15 and dt.minute >= 15

    def _allow_entry(self, bar: Bar) -> bool:
        dt = pd.Timestamp(bar.ts_event, unit='ns', tz='Asia/Kolkata')
        if dt.hour < 9 or (dt.hour == 9 and dt.minute < 45):
            return False
        if dt.hour >= 14 and dt.minute >= 30:
            return False
        return True

    def _is_bullish_engulfing(self, prev: Bar, bar: Bar) -> bool:
        return (prev.close < prev.open
            and bar.close > bar.open
            and bar.open <= prev.close
            and bar.close > prev.open)

    def on_bar(self, bar: Bar) -> None:
        if self._instrument is None or not self.indicators_initialized():
            return

        if not self.portfolio.is_flat(self._instrument_id):
            if self._is_market_closing(bar):
                self._exit_position(bar)
            return

        prev = self._prev_bar
        self._prev_bar = bar
        if prev is None:
            self._prev_rsi = self.rsi.value
            return

        if self._engulfing_bar is not None:
            if bar.close > self._engulfing_bar.close and bar.close > bar.open:
                if self._allow_entry(bar):
                    self._enter_position(bar)
            self._engulfing_prev = None
            self._engulfing_bar = None
            self._prev_rsi = self.rsi.value
            return

        if self._is_bullish_engulfing(prev, bar) and self._allow_entry(bar):
            if self._prev_rsi is not None and self._prev_rsi <= 0.5 < self.rsi.value:
                if bar.close.as_double() > self.sma20.value and bar.close.as_double() > self.vwap.value:
                    if bar.volume.as_double() > self.volume_sma.value * 1.5:
                        self._engulfing_prev = prev
                        self._engulfing_bar = bar

        self._prev_rsi = self.rsi.value

    def on_position_opened(self, event) -> None:
        if self._instrument is None or self.atr is None:
            return
        self._set_trailing_stop(event)

    def on_stop(self) -> None:
        self.cancel_all_orders(self._instrument_id)

    # --- helpers ---

    def _enter_position(self, bar: Bar) -> None:
        account = self.portfolio.account(venue=self._instrument_id.venue)
        equity = account.balance_total(account.base_currency)
        risk = Decimal(self.config.risk_percent)

        stop_price = Price(
            min(self._engulfing_prev.low.as_double(), self._engulfing_bar.low.as_double()),
            self._instrument.price_precision,
        )

        risk_amount = float(bar.close.as_double() - float(stop_price))
        tp_price = Price(
            bar.close.as_double() + risk_amount * 2.0,
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

        bracket = self.order_factory.bracket(
            instrument_id=self._instrument_id,
            order_side=OrderSide.BUY,
            quantity=qty,
            tp_price=tp_price,
            sl_trigger_price=stop_price,
        )
        self.submit_order_list(bracket)

    def _exit_position(self, bar: Bar) -> None:
        self.close_all_positions(
            self._instrument_id,
            reduce_only=True,
            tags=["EOD_SQUARE_OFF"],
        )

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
