from backtester.core import build_universe_from_symbols, build_universe_top_volatile
from backtester.core.runner import run_backtest
from backtester.core.models import StrategySpec, BenchmarkEntry
from backtester.strategy_variants import build_variant_configs_for_entry
from utility.file_storage import FileStorage

symbols = ["KOTYARK", "IFCI", "CUB", "BRIGADE", "CENTRUM", "NIITLTD", "TARSONS", "SPAL", "RAMCOSYS", "TCIEXP"]
entries = build_universe_from_symbols(symbols)
bench = BenchmarkEntry(symbol="NIFTY", upstox_key="NSE_INDEX|Nifty 50", instrument_id_str="NIFTY.NSE")
full_range = ("2024-07-01", "2026-07-07", "2025-09-27")

def run_test(desc, entry_name, exit_method, filters=None, rr_ratio=2.0):
    spec = StrategySpec(
        strategy_path='backtester.strategy_variants:VariantStrategy',
        config_path='backtester.strategy_variants:VariantConfig',
        config_builder=lambda u, c, b, en=entry_name, em=exit_method, fl=filters or [], rr=rr_ratio: (
            build_variant_configs_for_entry(u, c, b,
                entry_name=en, exit_method=em,
                filter_overrides=fl, rr_ratio=rr,
            )
        ),
    )
    r = run_backtest(
        universe=entries, benchmark=bench,
        t0=full_range[0], t1=full_range[1], t_split=full_range[2],
        spec=spec, interval='15minute', total_corpus='1000000 INR',
        catalog_path=FileStorage('catalog').root / '15minute',
        output_dir=FileStorage('backtest_results').root,
    )
    print(
        f"{desc:55s} "
        f"T:{r['# Trades'][0]:>4s}/{r['# Trades'][1]:>4s} "
        f"TrPnL:{r['Total PnL%'][0]:>10s} "
        f"ValPnL:{r['Total PnL%'][1]:>10s} "
        f"TrWR:{r['Win Rate'][0]:>6s} "
        f"ValWR:{r['Win Rate'][1]:>6s} "
        f"TrPF:{r['Profit Factor'][0]:>6s} "
        f"ValPF:{r['Profit Factor'][1]:>6s}"
    )

print("=" * 120)
print("BACKTEST: bearish_engulfing variants on 10-stock universe | Full range 2024-07-01 to 2026-07-07")
print("=" * 120)
print()

configs = [
    ("1. bear_engulf + fixed_rr + no_filt", "bearish_engulfing", "fixed_risk_reward", [], 2.0),
    ("2. bear_engulf + atr_trail + no_filt", "bearish_engulfing", "atr_trailing", [], 2.0),
    ("3. bear_engulf + keltner + no_filt", "bearish_engulfing", "keltner_trailing", [], 2.0),
    ("4. bear_engulf + chandelier + no_filt", "bearish_engulfing", "chandelier", [], 2.0),
    ("5. bear_engulf + 3:1_RR + no_filt", "bearish_engulfing", "fixed_risk_reward", [], 3.0),
    ("6. bear_engulf + vol_filt + fixed_rr", "bearish_engulfing", "fixed_risk_reward", ["volume_above_avg"], 2.0),
    ("7. bear_engulf + rsi_filt + fixed_rr", "bearish_engulfing", "fixed_risk_reward", ["rsi_above_50"], 2.0),
    ("8. shooting_star + fixed_rr", "shooting_star", "fixed_risk_reward", [], 2.0),
    ("9. death_cross + fixed_rr", "death_cross", "fixed_risk_reward", [], 2.0),
    ("10. rsi_overbought + fixed_rr", "rsi_overbought", "fixed_risk_reward", [], 2.0),
    ("11. three_black_crows + fixed_rr", "three_black_crows", "fixed_risk_reward", [], 2.0),
    ("12. bear_engulf + vol+rsi + fixed_rr", "bearish_engulfing", "fixed_risk_reward", ["volume_above_avg", "rsi_above_50"], 2.0),
]

for desc, entry, exit_m, filters, rr in configs:
    run_test(desc, entry, exit_m, filters, rr)

print()
print("=" * 120)
print("BACKTEST: top variants on n=50 top_volatile universe")
print("=" * 120)
print()

entries50, bench50 = build_universe_top_volatile(n=50)

full_specs = [
    ("A. bear_engulf + fixed_rr (n=50)", "bearish_engulfing", "fixed_risk_reward", [], 2.0),
    ("B. bear_engulf + atr_trail (n=50)", "bearish_engulfing", "atr_trailing", [], 2.0),
]
for desc, entry, exit_m, filters, rr in full_specs:
    spec = StrategySpec(
        strategy_path='backtester.strategy_variants:VariantStrategy',
        config_path='backtester.strategy_variants:VariantConfig',
        config_builder=lambda u, c, b, en=entry, em=exit_m, fl=filters or [], rr=rr: (
            build_variant_configs_for_entry(u, c, b,
                entry_name=en, exit_method=em,
                filter_overrides=fl, rr_ratio=rr,
            )
        ),
    )
    r = run_backtest(
        universe=entries50, benchmark=bench50,
        t0=full_range[0], t1=full_range[1], t_split=full_range[2],
        spec=spec, interval='15minute', total_corpus='1000000 INR',
        catalog_path=FileStorage('catalog').root / '15minute',
        output_dir=FileStorage('backtest_results').root,
    )
    print(
        f"{desc:55s} "
        f"T:{r['# Trades'][0]:>5s}/{r['# Trades'][1]:>5s} "
        f"TrPnL:{r['Total PnL%'][0]:>10s} "
        f"ValPnL:{r['Total PnL%'][1]:>10s}"
    )

print()
print("Done.")
