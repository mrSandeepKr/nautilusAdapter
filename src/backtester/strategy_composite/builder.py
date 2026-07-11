from __future__ import annotations

from nautilus_trader.trading.config import ImportableStrategyConfig

from backtester.core.models import UniverseEntry

from .registry import _COMPOSITE_ENTRIES


def build_composite_configs_for_entry(
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
        for v in _COMPOSITE_ENTRIES:
            if v["variant_name"] != entry_name or v["exit_method"] != exit_method:
                continue
            # Apply parameter overrides
            rr = rr_ratio if rr_ratio is not None else v["exit_params"]["rr_ratio"]
            am = atr_mult if atr_mult is not None else v["exit_params"]["atr_mult"]
            filters = filter_overrides if filter_overrides is not None else v["filters"]
            configs.append(ImportableStrategyConfig(
                strategy_path="backtester.strategy_composite:CompositeStrategy",
                config_path="backtester.strategy_composite:CompositeConfig",
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