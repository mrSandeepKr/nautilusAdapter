from __future__ import annotations

from decimal import Decimal

from nautilus_trader.backtest.models.fee import FeeModel
from nautilus_trader.common.config import NautilusConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.objects import Money


class NseIntradayFeeConfig(NautilusConfig, frozen=True):
    """Equity intraday (MIS): STT 0.025% on sell only."""
    stt_rate_sell: str = "0.00025"
    stt_rate_buy: str = "0.0"
    exchange_txn_rate: str = "0.0000307"
    sebi_rate: str = "0.000001"
    stamp_duty_rate_buy: str = "0.00003"
    brokerage_per_trade: str = "20"
    brokerage_pct: str = "0.0003"
    gst_rate: str = "0.18"


class NseSwingFeeConfig(NautilusConfig, frozen=True):
    """Equity delivery (CNC): STT 0.1% both sides, stamp duty 0.015% on buy."""
    stt_rate_sell: str = "0.001"
    stt_rate_buy: str = "0.001"
    exchange_txn_rate: str = "0.0000307"
    sebi_rate: str = "0.000001"
    stamp_duty_rate_buy: str = "0.00015"
    brokerage_per_trade: str = "20"
    brokerage_pct: str = "0.0003"
    gst_rate: str = "0.18"


class NseFeeModel(FeeModel):

    def __init__(self, config: NautilusConfig | None = None) -> None:
        self._config = config or NseIntradayFeeConfig()

    def get_commission(
        self,
        order,
        fill_qty,
        fill_px,
        instrument,
    ) -> Money:
        notional = instrument.notional_value(fill_qty, fill_px)
        notional_decimal = notional.as_decimal()
        cfg = self._config

        stt_sell = Decimal(cfg.stt_rate_sell)
        stt_buy = Decimal(cfg.stt_rate_buy)
        ex_rate = Decimal(cfg.exchange_txn_rate)
        sebi_rate = Decimal(cfg.sebi_rate)
        stamp_rate = Decimal(cfg.stamp_duty_rate_buy)
        brk_flat = Decimal(cfg.brokerage_per_trade)
        brk_pct = Decimal(cfg.brokerage_pct)
        gst_rate = Decimal(cfg.gst_rate)

        brokerage = min(brk_flat, notional_decimal * brk_pct)
        exchange_charges = notional_decimal * ex_rate
        sebi = notional_decimal * sebi_rate
        taxable = brokerage + exchange_charges + sebi
        gst = taxable * gst_rate

        stt = notional_decimal * (stt_buy if order.side == OrderSide.BUY else stt_sell)
        stamp = notional_decimal * stamp_rate if order.side == OrderSide.BUY else Decimal(0)

        total = stt + exchange_charges + sebi + stamp + brokerage + gst
        return Money(total, instrument.quote_currency)
