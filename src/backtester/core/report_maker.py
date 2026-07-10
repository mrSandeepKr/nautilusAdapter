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
    bar_spec: str,
) -> dict[str, tuple[str, str]]:
    _write_tearsheets(train_engine, validate_engine, nifty_ret, output_dir, bar_spec)

    comparison = build_comparison(train_result, validate_result)
    comparison["Verdict"] = verdict(comparison)

    pd.DataFrame.from_dict(comparison, orient="index").to_csv(
        output_dir / "comparison.csv"
    )
    print_comparison(comparison)

    inst_comp = build_instrument_comparison(train_engine.cache, validate_engine.cache)
    if inst_comp:
        pd.DataFrame.from_dict(inst_comp, orient="index").to_csv(
            output_dir / "instrument_comparison.csv"
        )
        _print_instrument_comparison(inst_comp)

    _print_output_links(output_dir)

    return comparison


def _instrument_metrics(cache) -> dict[str, dict[str, str]]:
    positions = cache.positions()
    by_inst: dict[str, list] = {}
    for pos in positions:
        if not pos.is_closed:
            continue
        inst = str(pos.instrument_id)
        by_inst.setdefault(inst, []).append(pos)

    metrics: dict[str, dict[str, str]] = {}
    for inst, pos_list in by_inst.items():
        pnls = [float(p.realized_pnl) for p in pos_list if p.realized_pnl is not None]
        if not pnls:
            continue
        winners = [p for p in pnls if p > 0]
        losers = [p for p in pnls if p <= 0]
        total = sum(pnls)
        n = len(pnls)
        win_rate = len(winners) / n
        avg_winner = sum(winners) / len(winners) if winners else 0.0
        avg_loser = sum(losers) / len(losers) if losers else 0.0
        pf = abs(sum(winners) / sum(losers)) if losers and sum(losers) != 0 else (float("inf") if winners else 0.0)
        metrics[inst] = {
            "Total PnL": f"₹{total:,.2f}",
            "Win Rate": f"{win_rate * 100:.1f}%",
            "# Trades": str(n),
            "Profit Factor": f"{pf:.2f}",
            "Avg Winner": f"₹{avg_winner:,.2f}",
            "Avg Loser": f"₹{avg_loser:,.2f}",
            "Expectancy": f"₹{total / n:,.2f}",
        }
    return metrics


def build_instrument_comparison(train_cache, validate_cache) -> dict[str, tuple[str, str]]:
    train_m = _instrument_metrics(train_cache)
    validate_m = _instrument_metrics(validate_cache)
    all_insts = sorted(set(train_m) | set(validate_m))
    comp: dict[str, tuple[str, str]] = {}
    for inst in all_insts:
        train_row = train_m.get(inst, {})
        validate_row = validate_m.get(inst, {})
        comp[inst] = (
            train_row.get("Total PnL", "N/A"),
            validate_row.get("Total PnL", "N/A"),
        )
    return comp


def _write_tearsheets(
    train_engine,
    validate_engine,
    nifty_ret: pd.Series | None,
    output_dir: Path,
    bar_spec: str,
) -> None:
    try:
        from nautilus_trader.analysis import (
            create_tearsheet,
            TearsheetConfig,
            TearsheetRunInfoChart,
            TearsheetStatsTableChart,
            TearsheetEquityChart,
            TearsheetDrawdownChart,
            TearsheetMonthlyReturnsChart,
            TearsheetDistributionChart,
            TearsheetRollingSharpeChart,
            TearsheetYearlyReturnsChart,
            TearsheetBarsWithFillsChart,
        )
    except ImportError:
        return

    full_config = TearsheetConfig(
        charts=[
            TearsheetRunInfoChart(),
            TearsheetStatsTableChart(),
            TearsheetEquityChart(),
            TearsheetDrawdownChart(),
            TearsheetMonthlyReturnsChart(),
            TearsheetDistributionChart(),
            TearsheetRollingSharpeChart(),
            TearsheetYearlyReturnsChart(),
        ],
        theme="nautilus_dark",
        height=2200,
    )

    for suffix, engine in [("train", train_engine), ("validate", validate_engine)]:
        create_tearsheet(
            engine,
            str(output_dir / f"tearsheet_{suffix}.html"),
            config=full_config,
            benchmark_returns=nifty_ret,
            benchmark_name="Nifty 50",
        )

    if not bar_spec:
        return

    inst_metrics = _instrument_metrics(train_engine.cache)
    top_insts = sorted(
        inst_metrics.items(),
        key=lambda x: abs(float(x[1]["Total PnL"].replace("₹", "").replace(",", ""))),
        reverse=True,
    )[:5]

    for inst, _ in top_insts:
        for suffix, engine in [("train", train_engine), ("validate", validate_engine)]:
            safe_inst = inst.replace(".", "_")
            out = output_dir / f"tearsheet_{safe_inst}_{suffix}.html"
            create_tearsheet(
                engine, str(out),
                config=TearsheetConfig(
                    charts=[
                        TearsheetRunInfoChart(),
                        TearsheetStatsTableChart(),
                        TearsheetEquityChart(title=f"{inst} — Equity"),
                        TearsheetBarsWithFillsChart(
                            bar_type=f"{inst}-{bar_spec}-EXTERNAL",
                            title=f"{inst} — Bars with Fills",
                        ),
                    ],
                    theme="nautilus_dark",
                    height=1400,
                ),
            )


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


def _print_instrument_comparison(comp: dict[str, tuple[str, str]]) -> None:
    print()
    print("=== Per-Instrument PnL Comparison ===")
    col_width = max(len(k) for k in comp) + 2
    print(f"{'Instrument'.ljust(col_width)}  {'Train':>15}  {'Validate':>15}")
    print("-" * (col_width + 32))
    for inst, (tv, vv) in comp.items():
        print(f"{inst.ljust(col_width)}  {tv:>15}  {vv:>15}")
    print()


def _print_output_links(output_dir: Path) -> None:
    abs_dir = output_dir.resolve()
    html_files = sorted(abs_dir.glob("*.html"))
    if not html_files:
        return
    print("=== Reports ===")
    for f in html_files:
        url = f"file://{f}"
        print(f"  {url}")
    print()
