from __future__ import annotations

from collections import deque
from collections.abc import Callable
from decimal import Decimal

import pandas as pd
from nautilus_trader.indicators import (
    AverageTrueRange,
    BollingerBands,
    DirectionalMovement,
    DonchianChannel,
    ExponentialMovingAverage,
    KeltnerChannel,
    MovingAverageConvergenceDivergence,
    RelativeStrengthIndex,
    SimpleMovingAverage,
    VolumeWeightedAveragePrice,
)
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price
from nautilus_trader.risk.sizing import FixedRiskSizer

from .config import CompositeConfig
from .exits import ExitMixin
from .signals import SignalMixin
from backtester.core.base_strategy import BaseStrategy


class CompositeStrategy(BaseStrategy, SignalMixin, ExitMixin):

    def __init__(self, config: CompositeConfig) -> None:
        super().__init__(config)
        self._instrument_id = InstrumentId.from_str(config.instrument_id_str)
        self._bar_type = BarType.from_str(config.bar_type_str)
        self._instrument = None
        self._sizer = None

        self.atr = None
        self.sma20 = None
        self.sma200 = None
        self.rsi = None
        self.vwap = None
        self.volume_sma = None
        self.ema9 = None
        self.ema21 = None
        self.macd = None
        self.adx = None
        self.bb = None
        self.kc = None
        self.dc = None

        self._prev_bar = None
        self._prev_prev_bar: Bar | None = None
        self._prev_rsi = None
        self._prev_macd = None
        self._prev_ema9 = None
        self._prev_ema21 = None
        self._prev_adx_val = None
        self._prev_di_pos = None
        self._prev_di_neg = None
        self._dx_buffer: deque[float] = deque(maxlen=14)
        self._computed_adx: float = 0.0
        self._signal_candle = None
        self._pending_stop_low: float | None = None
        self._pending_stop_high: float | None = None
        self._pending_entry_bar: Bar | None = None
        self._bb_bandwidth_prev = None
        self._bb_bandwidth_curr = None
        self._entry_bar = None
        self._entry_price = None

    @property
    def instrument_id(self) -> InstrumentId:
        return self._instrument_id

    def on_start(self) -> None:
        self._instrument = self.cache.instrument(self._instrument_id)
        if self._instrument is None:
            self.log.warning(f"Instrument {self._instrument_id} not found, skipping")
            return
        self._sizer = FixedRiskSizer(self._instrument)

        self.atr = AverageTrueRange(self.config.atr_period)
        self.sma20 = SimpleMovingAverage(20)
        self.sma200 = SimpleMovingAverage(200)
        self.rsi = RelativeStrengthIndex(14)
        self.vwap = VolumeWeightedAveragePrice()
        self.volume_sma = SimpleMovingAverage(10)
        self.ema9 = ExponentialMovingAverage(9)
        self.ema21 = ExponentialMovingAverage(21)
        self.macd = MovingAverageConvergenceDivergence(12, 26)
        self.adx = DirectionalMovement(14)
        self.bb = BollingerBands(20, 2.0)
        self.kc = KeltnerChannel(20, 2.0)
        self.dc = DonchianChannel(20)

        for ind in (
            self.atr,
            self.sma20,
            self.sma200,
            self.rsi,
            self.vwap,
            self.volume_sma,
            self.ema9,
            self.ema21,
            self.macd,
            self.adx,
            self.bb,
            self.kc,
            self.dc,
        ):
            self.register_indicator_for_bars(self._bar_type, ind)

        self.subscribe_bars(self._bar_type)

        self._long_dispatch: dict[str, Callable] = {
            "bullish_engulfing": self._signal_bullish_engulfing,
            "morning_star": lambda p, b: self._signal_morning_star([self._prev_prev_bar, self._prev_bar, b]),
            "ema_crossover": self._signal_ema_crossover,
            "rsi_oversold": self._signal_rsi_oversold,
            "volume_spike": self._signal_volume_spike,
            "donchian_breakout": self._signal_donchian_breakout,
            "supertrend": self._signal_supertrend,
            "vwap_bounce": self._signal_vwap_bounce,
            "macd_crossover": self._signal_macd_crossover,
            "adx_trend": self._signal_adx_trend,
            "rsi_macd_confluence": self._signal_rsi_macd_confluence,
            "bollinger_squeeze": self._signal_bollinger_squeeze,
            "hammer_reversal": self._signal_hammer_reversal,
            "piercing_pattern": self._signal_piercing_pattern,
            "three_soldiers": lambda p, b: self._signal_three_soldiers([self._prev_prev_bar, self._prev_bar, b]),
        }
        self._short_dispatch: dict[str, Callable] = {
            "bearish_engulfing": self._signal_bearish_engulfing,
            "shooting_star": self._signal_shooting_star,
            "three_black_crows": lambda p, b: self._signal_three_black_crows([self._prev_prev_bar, self._prev_bar, b]),
            "death_cross": self._signal_death_cross,
            "rsi_overbought": self._signal_rsi_overbought,
            "dark_cloud_cover": self._signal_dark_cloud_cover,
            "bearish_harami": self._signal_bearish_harami,
            "evening_star": lambda p, b: self._signal_evening_star([self._prev_prev_bar, self._prev_bar, b]),
        }

    def _macd_value(self) -> float:
        return self.macd.value

    def _to_ist(self, bar: Bar) -> pd.Timestamp:
        return pd.Timestamp(bar.ts_init, unit='ns', tz='Asia/Kolkata')

    def _allow_entry(self, bar: Bar) -> bool:
        dt = self._to_ist(bar)
        h_start, m_start = self.config.time_filter_start.split(":")
        h_end, m_end = self.config.time_filter_end.split(":")
        if dt.hour < int(h_start) or (dt.hour == int(h_start) and dt.minute < int(m_start)):
            return False
        if dt.hour > int(h_end) or (dt.hour == int(h_end) and dt.minute >= int(m_end)):
            return False
        return True

    def _check_filter(self, name: str, bar: Bar) -> bool:
        if name == "rsi_above_50":
            return self.rsi.value > 0.50
        if name == "above_vwap":
            return bar.close.as_double() > self.vwap.value
        if name == "above_sma20":
            return bar.close.as_double() > self.sma20.value
        if name == "above_sma200":
            return bar.close.as_double() > self.sma200.value
        if name == "volume_above_avg":
            return bar.volume.as_double() > self.volume_sma.value * 1.5
        if name == "adx_above_25":
            return self._computed_adx > 25.0
        return True

    def _check_filters(self, bar: Bar) -> bool:
        for f in self.config.filters:
            if not self._check_filter(f, bar):
                return False
        return True

    def _detect_entry(self, prev: Bar, bar: Bar) -> bool:
        fn = self._long_dispatch.get(self.config.variant_name)
        if fn is None:
            return False
        return fn(prev, bar)

    def _detect_entry_short(self, prev: Bar, bar: Bar) -> bool:
        fn = self._short_dispatch.get(self.config.variant_name)
        if fn is None:
            return False
        return fn(prev, bar)

    def _handle_bar(self, bar: Bar) -> None:
        if self._instrument is None or not self.indicators_initialized():
            return

        if not self.portfolio.is_flat(self._instrument_id):
            return

        prev = self._prev_bar
        self._compute_adx()

        if prev is None:
            self._prev_bar = bar
            self._prev_rsi = self.rsi.value
            self._prev_macd = self._macd_value()
            self._prev_ema9 = self.ema9.value
            self._prev_ema21 = self.ema21.value
            self._prev_adx_val = self.adx.value
            self._prev_di_pos = self.adx.pos
            self._prev_di_neg = self.adx.neg
            self._update_bb_bandwidth()
            return

        if not self._allow_entry(bar):
            self._prev_prev_bar = prev
            self._prev_bar = bar
            self._store_indicator_state()
            return

        if not self._check_filters(bar):
            self._prev_prev_bar = prev
            self._prev_bar = bar
            self._store_indicator_state()
            return

        if self.config.trade_direction == "SHORT":
            if self._detect_entry_short(prev, bar):
                self._enter_position(bar)
        elif self._detect_entry(prev, bar):
            self._enter_position(bar)

        self._prev_prev_bar = prev
        self._prev_bar = bar
        self._store_indicator_state()

    def _compute_adx(self) -> None:
        if not self.adx.initialized or not self.atr.initialized or self.atr.value <= 0.0:
            return
        di_pos = 100.0 * self.adx.pos / self.atr.value
        di_neg = 100.0 * self.adx.neg / self.atr.value
        di_sum = di_pos + di_neg
        if di_sum <= 0.0:
            return
        dx = 100.0 * abs(di_pos - di_neg) / di_sum
        self._dx_buffer.append(dx)
        if len(self._dx_buffer) >= 14:
            self._computed_adx = sum(self._dx_buffer) / len(self._dx_buffer)

    def _store_indicator_state(self) -> None:
        self._prev_rsi = self.rsi.value
        self._prev_macd = self._macd_value()
        self._prev_ema9 = self.ema9.value
        self._prev_ema21 = self.ema21.value
        self._prev_adx_val = self.adx.value
        self._prev_di_pos = self.adx.pos
        self._prev_di_neg = self.adx.neg
        self._update_bb_bandwidth()

    def _update_bb_bandwidth(self) -> None:
        self._bb_bandwidth_prev = self._bb_bandwidth_curr
        if self.bb.initialized:
            upper = self.bb.upper
            lower = self.bb.lower
            middle = self.bb.middle
            bw = (upper - lower) / middle if middle != 0.0 else 0.0
            self._bb_bandwidth_curr = bw

    def on_position_opened(self, event) -> None:
        if self._instrument is None or self.atr is None:
            return
        self._entry_bar = self._prev_bar
        self._entry_price = float(self._prev_bar.close.as_double()) if self._prev_bar else None
        self._set_trailing_stop(event)

    def on_stop(self) -> None:
        self.cancel_all_orders(self._instrument_id)
        self._signal_candle = None
        self._pending_stop_low = None
        self._pending_stop_high = None
        self._pending_entry_bar = None

    def _enter_position(self, bar: Bar) -> None:
        account = self.portfolio.account(venue=self._instrument_id.venue)
        equity = account.balance_total(account.base_currency)
        risk = Decimal(self.config.risk_percent)
        lot_size = Decimal(str(int(self._instrument.lot_size.as_double())))
        is_trailing = self.config.exit_method != "fixed_risk_reward"

        if self.config.trade_direction == "SHORT":
            stop_price = self._calc_entry_stop_short(bar)
            if stop_price is None:
                return
            risk_amount = float(stop_price) - float(bar.close.as_double())
            if risk_amount <= 0.0:
                return
            tp_price = Price(
                bar.close.as_double() - risk_amount * self.config.rr_ratio,
                self._instrument.price_precision,
            )
            order_side = OrderSide.SELL
        else:
            stop_price = self._calc_entry_stop_long(bar)
            risk_amount = float(bar.close.as_double() - float(stop_price))
            if risk_amount <= 0.0:
                return
            tp_price = Price(
                bar.close.as_double() + risk_amount * self.config.rr_ratio,
                self._instrument.price_precision,
            )
            order_side = OrderSide.BUY

        qty = self._sizer.calculate(
            entry=bar.close,
            stop_loss=stop_price,
            equity=equity,
            risk=risk,
            unit_batch_size=lot_size,
        )
        if qty.as_double() <= 0:
            return

        if is_trailing:
            bracket = self.order_factory.bracket(
                instrument_id=self._instrument_id,
                order_side=order_side,
                quantity=qty,
                tp_price=tp_price,
            )
        else:
            bracket = self.order_factory.bracket(
                instrument_id=self._instrument_id,
                order_side=order_side,
                quantity=qty,
                tp_price=tp_price,
                sl_trigger_price=stop_price,
            )
        self.submit_order_list(bracket)
        self._signal_candle = None
        self._pending_stop_low = None
        self._pending_stop_high = None