from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from nautilus_trader.model.enums import OrderSide, TrailingOffsetType, TriggerType
from nautilus_trader.model.objects import Price

if TYPE_CHECKING:
    from nautilus_trader.model.data import Bar


class ExitMixin:

    def _atr_offset(self) -> Decimal:
        return Decimal(str(round(
            self.atr.value * self.config.atr_mult,
            self._instrument.price_precision,
        )))

    def _calc_entry_stop_long(self, bar: Bar) -> Price:
        exit_m = self.config.exit_method
        if exit_m == "atr_trailing":
            return self._atr_trailing_entry_stop(bar)
        if exit_m == "keltner_trailing":
            return self._keltner_entry_stop(bar)
        if exit_m == "chandelier":
            return self._chandelier_entry_stop(bar)
        return self._fixed_rr_entry_stop(bar)

    def _atr_trailing_entry_stop(self, bar: Bar) -> Price:
        return Price(
            bar.close.as_double() - self.config.atr_mult * self.atr.value,
            self._instrument.price_precision,
        )

    def _keltner_entry_stop(self, bar: Bar) -> Price:
        return Price(self.kc.middle, self._instrument.price_precision)

    def _chandelier_entry_stop(self, bar: Bar) -> Price:
        return Price(
            self.dc.upper - 3.0 * self.atr.value,
            self._instrument.price_precision,
        )

    def _fixed_rr_entry_stop(self, bar: Bar) -> Price:
        if self._pending_stop_low is not None:
            return Price(self._pending_stop_low, self._instrument.price_precision)
        return Price(
            bar.close.as_double() - self.atr.value * self.config.atr_mult,
            self._instrument.price_precision,
        )

    def _calc_entry_stop_short(self, bar: Bar) -> Price | None:
        if self._pending_stop_high is None:
            return None
        return Price(self._pending_stop_high, self._instrument.price_precision)

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