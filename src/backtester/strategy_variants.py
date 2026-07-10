from __future__ import annotations

from collections import deque
from decimal import Decimal

import pandas as pd
from nautilus_trader.indicators import (
    AverageTrueRange,
    BollingerBands,
    CommodityChannelIndex,
    DirectionalMovement,
    DonchianChannel,
    ExponentialMovingAverage,
    KeltnerChannel,
    OnBalanceVolume,
    RelativeStrengthIndex,
    SimpleMovingAverage,
    VolumeWeightedAveragePrice,
    Stochastics,
)
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TrailingOffsetType, TriggerType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price
from nautilus_trader.risk.sizing import FixedRiskSizer
from nautilus_trader.trading.config import ImportableStrategyConfig, StrategyConfig
from nautilus_trader.trading.strategy import Strategy

from backtester.core.models import UniverseEntry

SHORT_SIGNALS = [
    "bearish_engulfing",
    "shooting_star",
    "three_black_crows",
    "death_cross",
    "rsi_overbought",
    "dark_cloud_cover",
    "bearish_harami",
    "evening_star",
]

VARIANT_NAMES = [
    "bullish_engulfing",
    "morning_star",
    "ema_crossover",
    "rsi_oversold",
    "volume_spike",
    "donchian_breakout",
    "supertrend",
    "vwap_bounce",
    "macd_crossover",
    "adx_trend",
    "rsi_macd_confluence",
    "bollinger_squeeze",
    "hammer_reversal",
    "piercing_pattern",
    "three_soldiers",
    # Short variants
    "bearish_engulfing",
    "shooting_star",
    "three_black_crows",
    "death_cross",
    "rsi_overbought",
    "dark_cloud_cover",
    "bearish_harami",
    "evening_star",
]


EXIT_METHODS = [
    "fixed_risk_reward",
    "atr_trailing",
    "keltner_trailing",
    "chandelier",
]


def _gen_variants() -> list[dict]:
    variants: list[dict] = []
    idx = 0

    # Default parameters
    default_rr = 2.0
    default_atr = 2.0
    default_filters = ["rsi_above_50", "volume_above_avg"]
    default_time = {"start": "09:45", "end": "14:30"}

    def _trade_direction(vname: str) -> str:
        return "SHORT" if vname in SHORT_SIGNALS else "LONG"

    # For each entry x exit, create ONE config with defaults
    for entry in VARIANT_NAMES:
        for exit_ in EXIT_METHODS:
            variants.append({
                "variant_name": entry,
                "entry_signal": entry,
                "entry_params": {},
                "exit_method": exit_,
                "exit_params": {"rr_ratio": default_rr, "atr_mult": default_atr},
                "filters": list(default_filters),
                "time_filter": dict(default_time),
                "universe_filter": {},
                "order_id_tag": f"V{idx:04d}",
                "trade_direction": _trade_direction(entry),
            })
            idx += 1

    # Also add a few extra configs: no filters, different RR ratios, no RSI filter
    # to test parameter sensitivity on a few key variants
    extra_entries = ["ema_crossover", "donchian_breakout", "bollinger_squeeze", "vwap_bounce", "rsi_oversold"]
    for entry in extra_entries:
        for exit_ in ["fixed_risk_reward", "atr_trailing"]:
            for rr in [1.5, 3.0]:
                variants.append({
                    "variant_name": entry,
                    "entry_signal": entry,
                    "entry_params": {},
                    "exit_method": exit_,
                    "exit_params": {"rr_ratio": rr, "atr_mult": default_atr},
                    "filters": [],
                    "time_filter": dict(default_time),
                    "universe_filter": {},
                    "order_id_tag": f"V{idx:04d}",
                    "trade_direction": _trade_direction(entry),
                })
                idx += 1

            # Test with vol filter only, and rsi filter only
            for filters in [["volume_above_avg"], ["rsi_above_50"]]:
                variants.append({
                    "variant_name": entry,
                    "entry_signal": entry,
                    "entry_params": {},
                    "exit_method": exit_,
                    "exit_params": {"rr_ratio": default_rr, "atr_mult": default_atr},
                    "filters": list(filters),
                    "time_filter": dict(default_time),
                    "universe_filter": {},
                    "order_id_tag": f"V{idx:04d}",
                    "trade_direction": _trade_direction(entry),
                })
                idx += 1

    # Add a few with different ATR multipliers
    for entry in ["bollinger_squeeze", "supertrend", "adx_trend"]:
        for atr_mult in [1.5, 3.0]:
            variants.append({
                "variant_name": entry,
                "entry_signal": entry,
                "entry_params": {},
                "exit_method": "atr_trailing",
                "exit_params": {"rr_ratio": default_rr, "atr_mult": atr_mult},
                "filters": list(default_filters),
                "time_filter": dict(default_time),
                "universe_filter": {},
                "order_id_tag": f"V{idx:04d}",
                "trade_direction": _trade_direction(entry),
            })
            idx += 1

    return variants


_VARIANTS = _gen_variants()


def build_variant_configs(
    universe: list[UniverseEntry],
    _close_prices: dict[str, float],
    bar_spec: str,
) -> list[ImportableStrategyConfig]:
    configs: list[ImportableStrategyConfig] = []
    for i, entry in enumerate(universe):
        for v in _VARIANTS:
            configs.append(ImportableStrategyConfig(
                strategy_path="backtester.strategy_variants:VariantStrategy",
                config_path="backtester.strategy_variants:VariantConfig",
                config={
                    "instrument_id_str": entry.instrument_id_str,
                    "bar_type_str": f"{entry.instrument_id_str}-{bar_spec}-EXTERNAL",
                    "risk_percent": "0.01",
                    "atr_period": 14,
                    "atr_mult": v["exit_params"]["atr_mult"],
                    "rr_ratio": v["exit_params"]["rr_ratio"],
                    "exit_method": v["exit_method"],
                    "variant_name": v["variant_name"],
                    "entry_params": v["entry_params"],
                    "filters": v["filters"],
                    "time_filter_start": v["time_filter"]["start"],
                    "time_filter_end": v["time_filter"]["end"],
                    "order_id_tag": f"{v['order_id_tag']}_{i:03d}",
                    "log_events": False,
                    "log_commands": False,
                    "force_eod_close": True,
                    "trade_direction": v.get("trade_direction", "LONG"),
                },
            ))
    return configs


def build_variant_configs_for_entry(
    universe: list[UniverseEntry],
    _close_prices: dict[str, float],
    bar_spec: str,
    *,
    entry_name: str,
    exit_method: str,
    rr_ratio: float | None = None,
    atr_mult: float | None = None,
    filter_overrides: list[str] | None = None,
) -> list[ImportableStrategyConfig]:
    configs: list[ImportableStrategyConfig] = []
    for i, entry in enumerate(universe):
        for v in _VARIANTS:
            if v["variant_name"] != entry_name or v["exit_method"] != exit_method:
                continue
            # Apply parameter overrides
            rr = rr_ratio if rr_ratio is not None else v["exit_params"]["rr_ratio"]
            am = atr_mult if atr_mult is not None else v["exit_params"]["atr_mult"]
            filters = filter_overrides if filter_overrides is not None else v["filters"]
            configs.append(ImportableStrategyConfig(
                strategy_path="backtester.strategy_variants:VariantStrategy",
                config_path="backtester.strategy_variants:VariantConfig",
                config={
                    "instrument_id_str": entry.instrument_id_str,
                    "bar_type_str": f"{entry.instrument_id_str}-{bar_spec}-EXTERNAL",
                    "risk_percent": "0.01",
                    "atr_period": 14,
                    "atr_mult": am,
                    "rr_ratio": rr,
                    "exit_method": v["exit_method"],
                    "variant_name": v["variant_name"],
                    "entry_params": v["entry_params"],
                    "filters": filters,
                    "time_filter_start": v["time_filter"]["start"],
                    "time_filter_end": v["time_filter"]["end"],
                    "order_id_tag": f"{v['order_id_tag']}_{i:03d}",
                    "log_events": False,
                    "log_commands": False,
                    "force_eod_close": True,
                    "trade_direction": v.get("trade_direction", "LONG"),
                },
            ))
            # Only use the first matching variant
            break
    return configs


class VariantConfig(StrategyConfig, frozen=True, kw_only=True):
    instrument_id_str: str
    bar_type_str: str
    risk_percent: str
    atr_period: int
    atr_mult: float
    rr_ratio: float
    exit_method: str
    variant_name: str
    entry_params: dict = {}
    filters: list[str] = []
    time_filter_start: str = "09:45"
    time_filter_end: str = "14:30"
    force_eod_close: bool = True
    trade_direction: str = "LONG"
    order_id_tag: str


class VariantStrategy(Strategy):

    def __init__(self, config: VariantConfig) -> None:
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
        self.adx = None
        self.bb = None
        self.kc = None
        self.dc = None
        self.stoch = None
        self.cci = None
        self.obv = None

        self._prev_bar = None
        self._prev_prev_bar: Bar | None = None
        self._prev_rsi = None
        self._prev_macd = None
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
        self.ema12 = ExponentialMovingAverage(12)
        self.ema26 = ExponentialMovingAverage(26)
        self.adx = DirectionalMovement(14)
        self.bb = BollingerBands(20, 2.0)
        self.kc = KeltnerChannel(20, 2.0)
        self.dc = DonchianChannel(20)
        self.stoch = Stochastics(14, 3, 3)
        self.cci = CommodityChannelIndex(20)
        self.obv = OnBalanceVolume()

        for ind in (
            self.atr,
            self.sma20,
            self.sma200,
            self.rsi,
            self.vwap,
            self.volume_sma,
            self.ema9,
            self.ema21,
            self.ema12,
            self.ema26,
            self.adx,
            self.bb,
            self.kc,
            self.dc,
            self.stoch,
            self.cci,
            self.obv,
        ):
            self.register_indicator_for_bars(self._bar_type, ind)

        self.subscribe_bars(self._bar_type)

    def _atr_offset(self) -> Decimal:
        return Decimal(str(round(
            self.atr.value * self.config.atr_mult,
            self._instrument.price_precision,
        )))

    def _macd_value(self) -> float:
        return self.ema12.value - self.ema26.value

    def _to_ist(self, bar: Bar) -> pd.Timestamp:
        return pd.Timestamp(bar.ts_event, unit='ns', tz='Asia/Kolkata')

    def _is_market_closing(self, bar: Bar) -> bool:
        dt = self._to_ist(bar)
        return dt.hour >= 15 and dt.minute >= 15

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

    def _signal_morning_star(self, bars: list[Bar | None]) -> bool:
        if len(bars) < 3:
            return False
        b1, b2, b3 = bars[-3], bars[-2], bars[-1]
        if b1 is None or b2 is None or b3 is None:
            return False
        b1_bearish = b1.close < b1.open
        b2_body = abs(b2.close.as_double() - b2.open.as_double())
        b2_range = b2.high.as_double() - b2.low.as_double()
        b2_small = b2_range > 0 and (b2_body / b2_range) < 0.3
        b3_bullish = b3.close > b3.open
        b3_close_above_b1_mid = b3.close.as_double() > (b1.high.as_double() + b1.low.as_double()) / 2.0
        return b1_bearish and b2_small and b3_bullish and b3_close_above_b1_mid

    def _signal_ema_crossover(self, prev: Bar, bar: Bar) -> bool:
        if prev is None:
            return False
        prev_close = prev.close.as_double()
        curr_close = bar.close.as_double()
        diff = curr_close - prev_close
        prev_ema9 = self.ema9.value - diff * (2.0 / 10.0)
        prev_ema21 = self.ema21.value - diff * (2.0 / 22.0)
        return prev_ema9 <= prev_ema21 and self.ema9.value > self.ema21.value

    def _signal_rsi_oversold(self, prev: Bar, bar: Bar) -> bool:
        if self._prev_rsi is None:
            return False
        return self._prev_rsi < 0.30 and self.rsi.value >= 0.30

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

    def _signal_hammer_reversal(self, prev: Bar, bar: Bar) -> bool:
        if self._signal_candle is None:
            body = abs(bar.close.as_double() - bar.open.as_double())
            wick_low = min(bar.open.as_double(), bar.close.as_double()) - bar.low.as_double()
            wick_high = bar.high.as_double() - max(bar.open.as_double(), bar.close.as_double())
            total = body + wick_low + wick_high
            if total > 0 and wick_low >= 2.0 * body and wick_high < body and bar.close > bar.open:
                self._signal_candle = bar
                self._pending_stop_low = min(bar.low.as_double(), prev.low.as_double())
            return False
        if bar.close > self._signal_candle.close and bar.close > bar.open:
            return True
        self._signal_candle = None
        self._pending_stop_low = None
        return False

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
        if self._signal_candle is None:
            if bar.close >= bar.open:
                return False
            body = abs(bar.close.as_double() - bar.open.as_double())
            wick_upper = bar.high.as_double() - max(bar.open.as_double(), bar.close.as_double())
            wick_lower = min(bar.open.as_double(), bar.close.as_double()) - bar.low.as_double()
            total = body + wick_upper + wick_lower
            if total > 0 and wick_upper >= 2.0 * body and wick_lower < body:
                self._signal_candle = bar
                self._pending_stop_high = bar.high.as_double()
            return False
        if bar.close < self._signal_candle.close and bar.close < bar.open:
            return True
        self._signal_candle = None
        self._pending_stop_high = None
        return False

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
        if prev is None:
            return False
        prev_close = prev.close.as_double()
        curr_close = bar.close.as_double()
        diff = curr_close - prev_close
        prev_ema9 = self.ema9.value - diff * (2.0 / 10.0)
        prev_ema21 = self.ema21.value - diff * (2.0 / 22.0)
        self._pending_stop_high = bar.high.as_double()
        return prev_ema9 >= prev_ema21 and self.ema9.value < self.ema21.value

    def _signal_rsi_overbought(self, prev: Bar, bar: Bar) -> bool:
        if self._prev_rsi is None:
            return False
        self._pending_stop_high = bar.high.as_double()
        return self._prev_rsi > 0.70 and self.rsi.value <= 0.70

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
        if len(bars) < 3:
            return False
        b1, b2, b3 = bars[-3], bars[-2], bars[-1]
        if b1 is None or b2 is None or b3 is None:
            return False
        b1_green = b1.close > b1.open
        b2_body = abs(b2.close.as_double() - b2.open.as_double())
        b2_range = b2.high.as_double() - b2.low.as_double()
        b2_small = b2_range > 0 and (b2_body / b2_range) < 0.3
        b3_red = b3.close < b3.open
        b1_mid = (b1.high.as_double() + b1.low.as_double()) / 2.0
        b3_close_below_b1_mid = b3.close.as_double() < b1_mid
        return b1_green and b2_small and b3_red and b3_close_below_b1_mid

    def _detect_entry_short(self, prev: Bar, bar: Bar) -> bool:
        dispatch_short = {
            "bearish_engulfing": self._signal_bearish_engulfing,
            "shooting_star": self._signal_shooting_star,
            "three_black_crows": lambda p, b: self._signal_three_black_crows([self._prev_prev_bar, self._prev_bar, b]),
            "death_cross": self._signal_death_cross,
            "rsi_overbought": self._signal_rsi_overbought,
            "dark_cloud_cover": self._signal_dark_cloud_cover,
            "bearish_harami": self._signal_bearish_harami,
            "evening_star": lambda p, b: self._signal_evening_star([self._prev_prev_bar, self._prev_bar, b]),
        }
        fn = dispatch_short.get(self.config.variant_name)
        if fn is None:
            return False
        return fn(prev, bar)

    def on_bar(self, bar: Bar) -> None:
        if self._instrument is None or not self.indicators_initialized():
            return

        if not self.portfolio.is_flat(self._instrument_id):
            if self.config.force_eod_close and self._is_market_closing(bar):
                self._exit_position(bar)
            return

        prev = self._prev_bar
        self._compute_adx()

        if prev is None:
            self._prev_bar = bar
            self._prev_rsi = self.rsi.value
            self._prev_macd = self._macd_value()
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

    def _detect_entry(self, prev: Bar, bar: Bar) -> bool:
        dispatch = {
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
        fn = dispatch.get(self.config.variant_name)
        if fn is None:
            return False
        return fn(prev, bar)

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

        if self.config.trade_direction == "SHORT":
            if self._pending_stop_high is None:
                return
            stop_price = Price(self._pending_stop_high, self._instrument.price_precision)
            risk_amount = float(stop_price) - float(bar.close.as_double())
            if risk_amount <= 0.0:
                return
            tp_price = Price(
                bar.close.as_double() - risk_amount * self.config.rr_ratio,
                self._instrument.price_precision,
            )
            order_side = OrderSide.SELL
        else:
            stop_price = self._calc_stop_price(bar)
            risk_amount = float(bar.close.as_double() - float(stop_price))
            if risk_amount <= 0.0:
                return
            tp_price = Price(
                bar.close.as_double() + risk_amount * self.config.rr_ratio,
                self._instrument.price_precision,
            )
            order_side = OrderSide.BUY

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
            order_side=order_side,
            quantity=qty,
            tp_price=tp_price,
            sl_trigger_price=stop_price,
        )
        self.submit_order_list(bracket)
        self._signal_candle = None
        self._pending_stop_low = None
        self._pending_stop_high = None

    def _calc_stop_price(self, bar: Bar) -> Price:
        exit_m = self.config.exit_method
        if exit_m == "atr_trailing" or exit_m == "keltner_trailing" or exit_m == "chandelier":
            atr_val = self.atr.value
            mult = self.config.atr_mult
            if exit_m == "atr_trailing":
                stop = bar.close.as_double() - mult * atr_val
            elif exit_m == "keltner_trailing":
                stop = self.kc.middle
            else:
                stop = self.dc.upper - 3.0 * atr_val
            return Price(stop, self._instrument.price_precision)
        if self._pending_stop_low is not None:
            return Price(self._pending_stop_low, self._instrument.price_precision)
        return Price(
            bar.close.as_double() - self.atr.value * self.config.atr_mult,
            self._instrument.price_precision,
        )

    def _exit_position(self, bar: Bar) -> None:
        self.close_all_positions(
            self._instrument_id,
            reduce_only=True,
            tags=["EOD_SQUARE_OFF"],
        )

    def _set_trailing_stop(self, event) -> None:
        if self.config.exit_method == "fixed_risk_reward":
            return
        is_short = self.config.trade_direction == "SHORT"
        offset = self._atr_offset()
        trailing = self.order_factory.trailing_stop_market(
            instrument_id=self._instrument_id,
            order_side=OrderSide.BUY if is_short else OrderSide.SELL,
            quantity=event.quantity,
            trailing_offset=offset,
            trailing_offset_type=TrailingOffsetType.PRICE,
            trigger_type=TriggerType.DEFAULT,
            reduce_only=True,
        )
        self.submit_order(trailing, position_id=event.position_id)
