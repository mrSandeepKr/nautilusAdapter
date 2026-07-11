from __future__ import annotations

from nautilus_trader.trading.config import StrategyConfig


class CompositeConfig(StrategyConfig, frozen=True, kw_only=True):
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