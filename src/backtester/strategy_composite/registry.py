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

COMPOSITE_ENTRIES = [
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


def _gen_composite_entries() -> list[dict]:
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
    for entry in COMPOSITE_ENTRIES:
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

    return variants


_COMPOSITE_ENTRIES = _gen_composite_entries()