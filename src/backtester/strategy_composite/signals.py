from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nautilus_trader.model.data import Bar


class SignalMixin:

    def _signal_bullish_engulfing(self, prev: Bar, bar: Bar) -> bool:
        if self._signal_candle is None:
            if prev.close < prev.open and bar.close > bar.open and bar.open <= prev.close and bar.close > prev.open:
                self._signal_candle = bar
                self._pending_stop_low = min(prev.low.as_double(), bar.low.as_double())
                self._pending_stop_high = max(prev.high.as_double(), bar.high.as_double())
            return False
        if bar.close > self._signal_candle.close and bar.close > bar.open:
            return True
        self._signal_candle = None
        self._pending_stop_low = None
        self._pending_stop_high = None
        return False

    def _signal_three_bar_star_impl(self, bars: list[Bar | None], *, short: bool) -> bool:
        if len(bars) < 3:
            return False
        b1, b2, b3 = bars[-3], bars[-2], bars[-1]
        if b1 is None or b2 is None or b3 is None:
            return False
        b2_body = abs(b2.close.as_double() - b2.open.as_double())
        b2_range = b2.high.as_double() - b2.low.as_double()
        b2_small = b2_range > 0 and (b2_body / b2_range) < 0.3
        b1_mid = (b1.high.as_double() + b1.low.as_double()) / 2.0
        if short:
            b1_green = b1.close > b1.open
            b3_red = b3.close < b3.open
            b3_close_below_b1_mid = b3.close.as_double() < b1_mid
            return b1_green and b2_small and b3_red and b3_close_below_b1_mid
        b1_bearish = b1.close < b1.open
        b3_bullish = b3.close > b3.open
        b3_close_above_b1_mid = b3.close.as_double() > b1_mid
        return b1_bearish and b2_small and b3_bullish and b3_close_above_b1_mid

    def _signal_morning_star(self, bars: list[Bar | None]) -> bool:
        return self._signal_three_bar_star_impl(bars, short=False)

    def _signal_ema_cross_impl(self, prev: Bar, bar: Bar, *, short: bool) -> bool:
        if prev is None or self._prev_ema9 is None or self._prev_ema21 is None:
            return False
        if short:
            self._pending_stop_high = bar.high.as_double()
            return self._prev_ema9 >= self._prev_ema21 and self.ema9.value < self.ema21.value
        return self._prev_ema9 <= self._prev_ema21 and self.ema9.value > self.ema21.value

    def _signal_ema_crossover(self, prev: Bar, bar: Bar) -> bool:
        return self._signal_ema_cross_impl(prev, bar, short=False)

    def _signal_rsi_cross_impl(self, prev: Bar, bar: Bar, *, short: bool) -> bool:
        if self._prev_rsi is None:
            return False
        if short:
            self._pending_stop_high = bar.high.as_double()
            return self._prev_rsi > 0.70 and self.rsi.value <= 0.70
        return self._prev_rsi < 0.30 and self.rsi.value >= 0.30

    def _signal_rsi_oversold(self, prev: Bar, bar: Bar) -> bool:
        return self._signal_rsi_cross_impl(prev, bar, short=False)

    def _signal_volume_spike(self, prev: Bar, bar: Bar) -> bool:
        price_ok = bar.close.as_double() > self.sma20.value
        vol_ok = bar.volume.as_double() > self.volume_sma.value * 2.0
        return price_ok and vol_ok

    def _signal_donchian_breakout(self, prev: Bar, bar: Bar) -> bool:
        return bar.close.as_double() > self.dc.upper

    def _signal_supertrend(self, prev: Bar, bar: Bar) -> bool:
        basic = (bar.high.as_double() + bar.low.as_double()) / 2.0
        lower = basic - self.config.atr_mult * self.atr.value
        return bar.close.as_double() > lower and bar.close.as_double() > bar.open.as_double()

    def _signal_vwap_bounce(self, prev: Bar, bar: Bar) -> bool:
        if prev is None:
            return False
        vwap_val = self.vwap.value
        return prev.close.as_double() < vwap_val and bar.close.as_double() > vwap_val

    def _signal_macd_crossover(self, prev: Bar, bar: Bar) -> bool:
        if self._prev_macd is None:
            return False
        return self._prev_macd < 0.0 and self._macd_value() >= 0.0

    def _signal_adx_trend(self, prev: Bar, bar: Bar) -> bool:
        return self._computed_adx > 25.0 and self.adx.pos > self.adx.neg

    def _signal_rsi_macd_confluence(self, prev: Bar, bar: Bar) -> bool:
        return self.rsi.value > 0.50 and self._macd_value() > 0.0

    def _signal_bollinger_squeeze(self, prev: Bar, bar: Bar) -> bool:
        lower = self.bb.lower
        middle = self.bb.middle
        upper = self.bb.upper
        bandwidth = (upper - lower) / middle if middle != 0.0 else 0.0
        if self._bb_bandwidth_prev is None or self._bb_bandwidth_curr is None:
            return False
        squeezed = self._bb_bandwidth_curr < self._bb_bandwidth_prev and bandwidth < 0.15
        breakout = bar.close.as_double() > upper
        return squeezed and breakout

    def _signal_reversal_wick_impl(self, prev: Bar, bar: Bar, *, short: bool) -> bool:
        if self._signal_candle is None:
            if short:
                if bar.close >= bar.open:
                    return False
            body = abs(bar.close.as_double() - bar.open.as_double())
            if short:
                wick_big = bar.high.as_double() - max(bar.open.as_double(), bar.close.as_double())
                wick_small = min(bar.open.as_double(), bar.close.as_double()) - bar.low.as_double()
            else:
                wick_big = min(bar.open.as_double(), bar.close.as_double()) - bar.low.as_double()
                wick_small = bar.high.as_double() - max(bar.open.as_double(), bar.close.as_double())
            total = body + wick_big + wick_small
            cond = total > 0 and wick_big >= 2.0 * body and wick_small < body
            if not short:
                cond = cond and bar.close > bar.open
            if cond:
                self._signal_candle = bar
                if short:
                    self._pending_stop_high = bar.high.as_double()
                else:
                    self._pending_stop_low = min(bar.low.as_double(), prev.low.as_double())
            return False
        if short:
            if bar.close < self._signal_candle.close and bar.close < bar.open:
                return True
            self._signal_candle = None
            self._pending_stop_high = None
            return False
        if bar.close > self._signal_candle.close and bar.close > bar.open:
            return True
        self._signal_candle = None
        self._pending_stop_low = None
        return False

    def _signal_hammer_reversal(self, prev: Bar, bar: Bar) -> bool:
        return self._signal_reversal_wick_impl(prev, bar, short=False)

    def _signal_piercing_pattern(self, prev: Bar, bar: Bar) -> bool:
        prev_bearish = prev.close < prev.open
        bar_bullish = bar.close > bar.open
        bar_opens_below_prev_close = bar.open.as_double() < prev.close.as_double()
        bar_closes_above_prev_mid = bar.close.as_double() > (prev.open.as_double() + prev.close.as_double()) / 2.0
        bar_closes_below_prev_open = bar.close.as_double() < prev.open.as_double()
        return prev_bearish and bar_bullish and bar_opens_below_prev_close and bar_closes_above_prev_mid and bar_closes_below_prev_open

    def _signal_three_soldiers(self, bars: list[Bar | None]) -> bool:
        if len(bars) < 3:
            return False
        b1, b2, b3 = bars[-3], bars[-2], bars[-1]
        if b1 is None or b2 is None or b3 is None:
            return False
        return (
            b1.close > b1.open and b2.close > b2.open and b3.close > b3.open
            and b2.close.as_double() > b1.close.as_double()
            and b3.close.as_double() > b2.close.as_double()
            and b2.open.as_double() > b1.open.as_double()
            and b3.open.as_double() > b2.open.as_double()
            and b2.close.as_double() < b2.high.as_double()
            and b3.close.as_double() < b3.high.as_double()
        )

    def _signal_bearish_engulfing(self, prev: Bar, bar: Bar) -> bool:
        if self._signal_candle is None:
            if prev.close > prev.open and bar.close < bar.open and bar.open >= prev.close and bar.close < prev.open:
                self._signal_candle = bar
                self._pending_stop_low = min(prev.low.as_double(), bar.low.as_double())
                self._pending_stop_high = max(prev.high.as_double(), bar.high.as_double())
            return False
        if bar.close < self._signal_candle.close and bar.close < bar.open:
            return True
        self._signal_candle = None
        self._pending_stop_low = None
        self._pending_stop_high = None
        return False

    def _signal_shooting_star(self, prev: Bar, bar: Bar) -> bool:
        return self._signal_reversal_wick_impl(prev, bar, short=True)

    def _signal_three_black_crows(self, bars: list[Bar | None]) -> bool:
        if len(bars) < 3:
            return False
        b1, b2, b3 = bars[-3], bars[-2], bars[-1]
        if b1 is None or b2 is None or b3 is None:
            return False
        if not (b1.close < b1.open and b2.close < b2.open and b3.close < b3.open):
            return False
        if not (b2.close.as_double() < b1.close.as_double() and b3.close.as_double() < b2.close.as_double()):
            return False
        if not (b2.open.as_double() < b1.open.as_double() and b3.open.as_double() < b2.open.as_double()):
            return False
        self._pending_stop_high = max(b1.high.as_double(), b2.high.as_double(), b3.high.as_double())
        return True

    def _signal_death_cross(self, prev: Bar, bar: Bar) -> bool:
        return self._signal_ema_cross_impl(prev, bar, short=True)

    def _signal_rsi_overbought(self, prev: Bar, bar: Bar) -> bool:
        return self._signal_rsi_cross_impl(prev, bar, short=True)

    def _signal_dark_cloud_cover(self, prev: Bar, bar: Bar) -> bool:
        if self._signal_candle is None:
            prev_green = prev.close > prev.open
            bar_red = bar.close < bar.open
            opens_above_prev_close = bar.open.as_double() >= prev.close.as_double()
            prev_mid = (prev.open.as_double() + prev.close.as_double()) / 2.0
            closes_below_prev_mid = bar.close.as_double() < prev_mid
            if prev_green and bar_red and opens_above_prev_close and closes_below_prev_mid:
                self._signal_candle = bar
                self._pending_stop_high = max(prev.high.as_double(), bar.high.as_double())
            return False
        if bar.close < self._signal_candle.close and bar.close < bar.open:
            return True
        self._signal_candle = None
        self._pending_stop_high = None
        return False

    def _signal_bearish_harami(self, prev: Bar, bar: Bar) -> bool:
        if self._signal_candle is None:
            prev_green = prev.close > prev.open
            bar_red = bar.close < bar.open
            bar_inside_prev = bar.high.as_double() <= prev.high.as_double() and bar.low.as_double() >= prev.low.as_double()
            prev_body = abs(prev.close.as_double() - prev.open.as_double())
            bar_body = abs(bar.close.as_double() - bar.open.as_double())
            bar_smaller = bar_body < prev_body * 0.6
            if prev_green and bar_red and bar_inside_prev and bar_smaller:
                self._signal_candle = bar
                self._pending_stop_high = prev.high.as_double()
            return False
        if bar.close < self._signal_candle.close and bar.close < bar.open:
            return True
        self._signal_candle = None
        self._pending_stop_high = None
        return False

    def _signal_evening_star(self, bars: list[Bar | None]) -> bool:
        return self._signal_three_bar_star_impl(bars, short=True)