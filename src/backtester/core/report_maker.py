from __future__ import annotations

from pathlib import Path

import pandas as pd


def make_report(
    train_engine,
    validate_engine,
    train_result,
    validate_result,
    nifty_ret: pd.Series | None,
    output_dir: Path,
) -> dict[str, tuple[str, str]]:
    _write_tearsheets(train_engine, validate_engine, nifty_ret, output_dir)

    comparison = build_comparison(train_result, validate_result)
    comparison["Verdict"] = verdict(comparison)

    pd.DataFrame.from_dict(comparison, orient="index").to_csv(
        output_dir / "comparison.csv"
    )
    print_comparison(comparison)

    return comparison


def _write_tearsheets(
    train_engine,
    validate_engine,
    nifty_ret: pd.Series | None,
    output_dir: Path,
) -> None:
    try:
        from nautilus_trader.analysis import create_tearsheet

        create_tearsheet(
            train_engine,
            str(output_dir / "tearsheet_train.html"),
            benchmark_returns=nifty_ret,
            benchmark_name="Nifty 50",
        )
        create_tearsheet(
            validate_engine,
            str(output_dir / "tearsheet_validate.html"),
            benchmark_returns=nifty_ret,
            benchmark_name="Nifty 50",
        )
    except ImportError:
        pass


def build_comparison(
    train_result,
    validate_result,
) -> dict[str, tuple[str, str]]:
    def _metrics(r) -> dict[str, str]:
        pnl = r.stats_pnls.get("INR", {})
        ret = r.stats_returns
        return {
            "Total PnL%": f"{pnl.get('PnL% (total)', 0):.4f}%",
            "Win Rate": f"{pnl.get('Win Rate', 0) * 100:.1f}%",
            "# Trades": str(r.total_positions),
            "Profit Factor": f"{ret.get('Profit Factor', 0):.2f}",
            "SharpeRatio (ann)": f"{ret.get('Sharpe Ratio (252 days)', 0):.4f}",
            "SortinoRatio": f"{ret.get('Sortino Ratio (252 days)', 0):.4f}",
            "AvgWinner": f"₹{pnl.get('Avg Winner', 0):,.2f}",
            "AvgLoser": f"₹{pnl.get('Avg Loser', 0):,.2f}",
            "Expectancy (₹)": f"₹{pnl.get('Expectancy', 0):,.2f}",
        }

    train_m = _metrics(train_result)
    validate_m = _metrics(validate_result)

    return {k: (train_m[k], validate_m[k]) for k in train_m}


def verdict(comparison: dict[str, tuple[str, str]]) -> tuple[str, str]:
    v = comparison.get("Win Rate", ("0%", "0%"))[1]
    wr = float(v.strip("%"))
    pf_str = comparison.get("Profit Factor", ("0", "0"))[1]
    pf = float(pf_str)
    pnl_str = comparison.get("Total PnL%", ("0%", "0%"))[1]
    pnl = float(pnl_str.strip("%"))
    result = "CONFIRMED" if wr > 50 and pf > 1.0 and pnl > 0 else "DENIED"
    return (result, result)


def print_comparison(comparison: dict[str, tuple[str, str]]) -> None:
    col_width = max(len(k) for k in comparison) + 2
    print(f"{'Metric'.ljust(col_width)}  {'Train':>22}  {'Validate':>22}")
    print("-" * (col_width + 48))
    for key, (train_val, validate_val) in comparison.items():
        print(f"{key.ljust(col_width)}  {train_val:>22}  {validate_val:>22}")
