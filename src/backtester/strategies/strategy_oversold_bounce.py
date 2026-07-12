from __future__ import annotations

from decimal import Decimal

from nautilus_trader.indicators import (
    AverageTrueRange,
    ExponentialMovingAverage,
    RelativeStrengthIndex,
)
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price
from nautilus_trader.risk.sizing import FixedRiskSizer
from nautilus_trader.trading.config import ImportableStrategyConfig

from backtester.core.base_strategy import BaseConfig, BaseStrategy
from backtester.core.models import TradeStyle, UniverseEntry


class SwingConfig(BaseConfig, frozen=True, kw_only=True):
    instrument_id_str: str
    bar_type_str: str
    risk_percent: str = "0.01"
    order_id_tag: str = "SWING"
    force_eod_close: bool


class SwingStrategy(BaseStrategy):

    # ponytail: SL at 1×ATR; promote to config only if trailing variants appear
    _STOP_ATR_MULT = 1.0
    # ponytail: fallback TP multiplier when EMA20 is below entry (rare on daily)
    _FALLBACK_TP_R = 1.5

    def __init__(self, config: SwingConfig) -> None:
        super().__init__(config)
        self._instrument_id = InstrumentId.from_str(config.instrument_id_str)
        self._bar_type = BarType.from_str(config.bar_type_str)
        self._instrument = None
        self._sizer = None
        self.atr = None
        self.rsi = None
        self.ema20 = None

    @property
    def instrument_id(self) -> InstrumentId:
        return self._instrument_id

    def on_start(self) -> None:
        self._instrument = self.cache.instrument(self._instrument_id)
        if self._instrument is None:
            self.log.warning(f"Instrument {self._instrument_id} not found, skipping")
            return
        self._sizer = FixedRiskSizer(self._instrument)

        self.atr = AverageTrueRange(14)
        self.rsi = RelativeStrengthIndex(14)
        self.ema20 = ExponentialMovingAverage(20)

        for ind in (self.atr, self.rsi, self.ema20):
            self.register_indicator_for_bars(self._bar_type, ind)

        self.subscribe_bars(self._bar_type)

    def _handle_bar(self, bar: Bar) -> None:
        if self._instrument is None or not self.indicators_initialized():
            return
        if self.cache.bar_count(self._bar_type) < 5:
            return

        if not self.portfolio.is_flat(self._instrument_id):
            return

        close = bar.close.as_double()
        ema20_val = self.ema20.value
        atr_val = self.atr.value
        rsi_val = self.rsi.value
        if atr_val <= 0 or ema20_val <= 0:
            return

        # Buy when price is stretched below EMA20 (oversold + reversal)
        deviation = (close - ema20_val) / atr_val
        if deviation < -1.5 and rsi_val < 0.30 and close > bar.open.as_double():
            self._enter(bar)

    def on_stop(self) -> None:
        self.cancel_all_orders(self._instrument_id)

    def _enter(self, bar: Bar) -> None:
        account = self.portfolio.account(venue=self._instrument_id.venue)
        equity = account.balance_total(account.base_currency)
        risk = Decimal(self.config.risk_percent)
        lot_size = Decimal(str(int(self._instrument.lot_size.as_double())))

        entry_price = bar.close.as_double()
        ema20_val = self.ema20.value
        atr_val = self.atr.value

        stop_price = Price(
            entry_price - atr_val * self._STOP_ATR_MULT,
            self._instrument.price_precision,
        )
        risk_amount = entry_price - float(stop_price)
        if risk_amount <= 0.0:
            return

        # TP: mean reversion to EMA20; fallback to 1.5R extension if EMA is below entry
        tp_price = Price(
            ema20_val if ema20_val > entry_price
            else entry_price + risk_amount * self._FALLBACK_TP_R,
            self._instrument.price_precision,
        )

        qty = self._sizer.calculate(
            entry=bar.close,
            stop_loss=stop_price,
            equity=equity,
            risk=risk,
            unit_batch_size=lot_size,
        )
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


def build_swing_configs(
    universe: list[UniverseEntry],
    _close_prices: dict[str, float],
    bar_spec: str,
    trade_style: TradeStyle,
) -> list[ImportableStrategyConfig]:
    force_eod = trade_style == TradeStyle.INTRADAY
    configs = []
    for i, entry in enumerate(universe):
        configs.append(ImportableStrategyConfig(
            strategy_path="backtester.strategy_swing:SwingStrategy",
            config_path="backtester.strategy_swing:SwingConfig",
            config={
                "instrument_id_str": entry.instrument_id_str,
                "bar_type_str": f"{entry.instrument_id_str}-{bar_spec}-EXTERNAL",
                "order_id_tag": f"SWING_{i:03d}",
                "force_eod_close": force_eod,
            },
        ))
    return configs
