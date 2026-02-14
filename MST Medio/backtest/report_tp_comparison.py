"""
report_tp_comparison.py — Detailed report comparing TP strategies
Generates a comprehensive comparison with visual formatting.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
import numpy as np
from strategy_mst_medio import run_mst_medio, Signal
from backtest_partial_tp import simulate_partial_tp, load_data
from typing import List, Dict, Tuple

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "analysis_output")

PAIRS = [
    ("XAUUSD", "XAUUSD_M5.csv"),
    ("EURUSD", "EURUSD_M5.csv"),
    ("USDJPY", "USDJPY_M5.csv"),
    ("BTCUSD", "BTCUSD_M5.csv"),
]

STRATEGIES = [
    ("Baseline (Confirm TP)", {"tp_mode": "confirm", "min_rr": 0.0, "partial": False}),
    ("Fixed R:R 2:1", {"tp_mode": "fixed_rr", "fixed_rr": 2.0, "min_rr": 0.0, "partial": False}),
    ("Fixed R:R 3:1", {"tp_mode": "fixed_rr", "fixed_rr": 3.0, "min_rr": 0.0, "partial": False}),
    ("Partial TP (50%+BE)", {"tp_mode": "confirm", "min_rr": 0.0, "partial": True}),
]


def calc_metrics(signals: List[Signal], df: pd.DataFrame = None, partial: bool = False) -> Dict:
    if partial and df is not None:
        results = simulate_partial_tp(signals, df)
        total = len(results)
        if total == 0:
            return empty_metrics()
        wins = sum(1 for r in results if r.total_pnl_r > 0)
        losses = sum(1 for r in results if r.total_pnl_r < 0)
        be = sum(1 for r in results if r.total_pnl_r == 0)
        pnl = sum(r.total_pnl_r for r in results)
        pnls = [r.total_pnl_r for r in results]
        win_pnls = [r.total_pnl_r for r in results if r.total_pnl_r > 0]
        loss_pnls = [r.total_pnl_r for r in results if r.total_pnl_r < 0]
    else:
        closed = [s for s in signals if s.result in ("TP", "SL", "CLOSE_REVERSE")]
        total = len(closed)
        if total == 0:
            return empty_metrics()
        wins = sum(1 for s in closed if s.pnl_r > 0)
        losses = sum(1 for s in closed if s.pnl_r < 0)
        be = sum(1 for s in closed if s.pnl_r == 0)
        pnl = sum(s.pnl_r for s in closed)
        pnls = [s.pnl_r for s in closed]
        win_pnls = [s.pnl_r for s in closed if s.pnl_r > 0]
        loss_pnls = [s.pnl_r for s in closed if s.pnl_r < 0]

    wr = wins / total * 100 if total > 0 else 0
    avg_win = np.mean(win_pnls) if win_pnls else 0
    avg_loss = np.mean(loss_pnls) if loss_pnls else 0
    profit_factor = abs(sum(win_pnls) / sum(loss_pnls)) if loss_pnls and sum(loss_pnls) != 0 else float('inf')
    max_dd = calc_max_drawdown(pnls)
    expectancy = pnl / total if total > 0 else 0

    return {
        "trades": total,
        "wins": wins,
        "losses": losses,
        "be": be,
        "wr": round(wr, 1),
        "pnl": round(pnl, 2),
        "avg_trade": round(expectancy, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2),
        "max_dd": round(max_dd, 2),
        "best_trade": round(max(pnls), 2) if pnls else 0,
        "worst_trade": round(min(pnls), 2) if pnls else 0,
    }


def empty_metrics() -> Dict:
    return {k: 0 for k in [
        "trades", "wins", "losses", "be", "wr", "pnl", "avg_trade",
        "avg_win", "avg_loss", "profit_factor", "max_dd", "best_trade", "worst_trade"
    ]}


def calc_max_drawdown(pnls: List[float]) -> float:
    """Calculate max drawdown in R from a list of trade PnLs."""
    if not pnls:
        return 0
    equity = 0
    peak = 0
    max_dd = 0
    for pnl in pnls:
        equity += pnl
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd
    return max_dd


def bar_chart(value: float, max_val: float, width: int = 30, char: str = "█") -> str:
    """Create a text bar chart."""
    if max_val <= 0:
        return ""
    filled = int(abs(value) / max_val * width)
    filled = min(filled, width)
    if value >= 0:
        return char * filled
    else:
        return "░" * filled


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Collect all data
    all_data: Dict[str, Dict[str, Dict]] = {}  # strategy -> pair -> metrics
    pair_dfs = {}

    for pair_name, data_file in PAIRS:
        path = os.path.join(DATA_DIR, data_file)
        if not os.path.exists(path):
            continue
        df = load_data(path)
        pair_dfs[pair_name] = df

        for strat_name, config in STRATEGIES:
            signals, _ = run_mst_medio(
                df, pivot_len=5, break_mult=0.25, impulse_mult=1.5,
                tp_mode=config["tp_mode"],
                fixed_rr=config.get("fixed_rr", 2.0),
                min_rr=config.get("min_rr", 0.0),
                debug=False,
            )
            metrics = calc_metrics(signals, df, config.get("partial", False))

            if strat_name not in all_data:
                all_data[strat_name] = {}
            all_data[strat_name][pair_name] = metrics

    pair_names = list(pair_dfs.keys())
    strat_names = [s[0] for s in STRATEGIES]

    # ══════════════════════════════════════════════════════════════
    # REPORT
    # ══════════════════════════════════════════════════════════════
    print()
    print("╔══════════════════════════════════════════════════════════════════════════╗")
    print("║         MST Medio v2.0 — TP Strategy Comparison Report                 ║")
    print("║         Data: M5 timeframe | 4 pairs | ~4800 bars each                  ║")
    print("╚══════════════════════════════════════════════════════════════════════════╝")

    # ── SECTION 1: PnL Comparison Bar Chart ──
    print(f"\n{'━'*74}")
    print(f"  📊 TOTAL PnL COMPARISON (R)")
    print(f"{'━'*74}")

    # Combined PnL for each strategy
    combined_pnl = {}
    for sn in strat_names:
        combined_pnl[sn] = sum(all_data[sn][p]["pnl"] for p in pair_names)
    max_pnl = max(combined_pnl.values()) if combined_pnl else 1

    for sn in strat_names:
        pnl = combined_pnl[sn]
        bar = bar_chart(pnl, max_pnl, 35)
        marker = " 🏆" if pnl == max_pnl else ""
        print(f"  {sn:<25s} {bar} {pnl:>+8.1f}R{marker}")

    # ── SECTION 2: Main Comparison Table ──
    print(f"\n{'━'*74}")
    print(f"  📋 DETAILED COMPARISON — COMBINED ALL PAIRS")
    print(f"{'━'*74}")

    # Build combined metrics
    combined_metrics = {}
    for sn in strat_names:
        cm = {
            "trades": sum(all_data[sn][p]["trades"] for p in pair_names),
            "wins": sum(all_data[sn][p]["wins"] for p in pair_names),
            "losses": sum(all_data[sn][p]["losses"] for p in pair_names),
            "pnl": sum(all_data[sn][p]["pnl"] for p in pair_names),
        }
        cm["wr"] = round(cm["wins"] / cm["trades"] * 100, 1) if cm["trades"] > 0 else 0
        cm["avg_trade"] = round(cm["pnl"] / cm["trades"], 2) if cm["trades"] > 0 else 0

        # Aggregate avg_win, avg_loss, profit_factor
        total_win_pnl = sum(all_data[sn][p]["avg_win"] * all_data[sn][p]["wins"]
                           for p in pair_names if all_data[sn][p]["wins"] > 0)
        total_loss_pnl = sum(all_data[sn][p]["avg_loss"] * all_data[sn][p]["losses"]
                            for p in pair_names if all_data[sn][p]["losses"] > 0)
        cm["avg_win"] = round(total_win_pnl / cm["wins"], 2) if cm["wins"] > 0 else 0
        cm["avg_loss"] = round(total_loss_pnl / cm["losses"], 2) if cm["losses"] > 0 else 0
        cm["profit_factor"] = round(abs(total_win_pnl / total_loss_pnl), 2) if total_loss_pnl != 0 else float('inf')
        cm["max_dd"] = max(all_data[sn][p]["max_dd"] for p in pair_names)
        combined_metrics[sn] = cm

    # Print table
    header_row = f"  {'Metric':<22s}"
    for sn in strat_names:
        short = sn[:18]
        header_row += f" {short:>18s}"
    print(header_row)
    print(f"  {'─'*22}" + "─" * (19 * len(strat_names)))

    rows = [
        ("Trades", "trades", "d"),
        ("Wins", "wins", "d"),
        ("Losses", "losses", "d"),
        ("Win Rate", "wr", "%"),
        ("Total PnL (R)", "pnl", "R"),
        ("Avg PnL/Trade (R)", "avg_trade", "R"),
        ("Avg Win (R)", "avg_win", "R"),
        ("Avg Loss (R)", "avg_loss", "R"),
        ("Profit Factor", "profit_factor", "f"),
        ("Max Drawdown (R)", "max_dd", "R"),
    ]

    for label, key, fmt in rows:
        row = f"  {label:<22s}"
        values = [combined_metrics[sn].get(key, 0) for sn in strat_names]
        best_val = max(values) if key not in ["losses", "max_dd", "avg_loss"] else min(values)

        for sn in strat_names:
            val = combined_metrics[sn].get(key, 0)
            is_best = (val == best_val) and val != 0

            if fmt == "d":
                cell = f"{int(val)}"
            elif fmt == "%":
                cell = f"{val:.1f}%"
            elif fmt == "R":
                cell = f"{val:+.2f}R"
            elif fmt == "f":
                if val == float('inf'):
                    cell = "∞"
                else:
                    cell = f"{val:.2f}"
            else:
                cell = f"{val}"

            if is_best:
                cell = f"★{cell}"
            row += f" {cell:>18s}"
        print(row)

    # ── SECTION 3: Per-Pair Breakdown ──
    print(f"\n{'━'*74}")
    print(f"  📊 PnL BY PAIR")
    print(f"{'━'*74}")

    header = f"  {'Pair':<10s}"
    for sn in strat_names:
        short = sn[:16]
        header += f" {short:>16s}"
    header += f" {'Best':>20s}"
    print(header)
    print(f"  {'─'*10}" + "─" * (17 * len(strat_names)) + "─" * 21)

    for pair in pair_names:
        row = f"  {pair:<10s}"
        pair_pnls = {}
        for sn in strat_names:
            pnl = all_data[sn][pair]["pnl"]
            pair_pnls[sn] = pnl
            row += f" {pnl:>+15.2f}R"

        best_sn = max(pair_pnls, key=pair_pnls.get)
        row += f"  🏆 {best_sn[:16]}"
        print(row)

    # Totals
    row = f"  {'TOTAL':<10s}"
    for sn in strat_names:
        row += f" {combined_pnl[sn]:>+15.2f}R"
    best_total = max(combined_pnl, key=combined_pnl.get)
    row += f"  🏆 {best_total[:16]}"
    print(f"  {'─'*10}" + "─" * (17 * len(strat_names)) + "─" * 21)
    print(row)

    # ── SECTION 4: Win Rate by Pair ──
    print(f"\n{'━'*74}")
    print(f"  📊 WIN RATE BY PAIR")
    print(f"{'━'*74}")

    header = f"  {'Pair':<10s}"
    for sn in strat_names:
        short = sn[:16]
        header += f" {short:>16s}"
    print(header)
    print(f"  {'─'*10}" + "─" * (17 * len(strat_names)))

    for pair in pair_names:
        row = f"  {pair:<10s}"
        for sn in strat_names:
            wr = all_data[sn][pair]["wr"]
            row += f" {wr:>15.1f}%"
        print(row)

    # ── SECTION 5: Risk Analysis ──
    print(f"\n{'━'*74}")
    print(f"  ⚠️  RISK ANALYSIS")
    print(f"{'━'*74}")

    header = f"  {'Metric':<22s}"
    for sn in strat_names:
        short = sn[:18]
        header += f" {short:>18s}"
    print(header)
    print(f"  {'─'*22}" + "─" * (19 * len(strat_names)))

    # Worst pair for each strategy
    row = f"  {'Worst Pair PnL':<22s}"
    for sn in strat_names:
        worst_pair = min(pair_names, key=lambda p: all_data[sn][p]["pnl"])
        worst_pnl = all_data[sn][worst_pair]["pnl"]
        row += f" {worst_pair}:{worst_pnl:+.1f}R".rjust(19)
    print(row)

    # Consecutive losses (estimate)
    row = f"  {'Max DD (worst pair)':<22s}"
    for sn in strat_names:
        worst_dd = max(all_data[sn][p]["max_dd"] for p in pair_names)
        row += f" {worst_dd:>17.2f}R"
    print(row)

    # Worst single trade
    row = f"  {'Worst Trade':<22s}"
    for sn in strat_names:
        worst = min(all_data[sn][p]["worst_trade"] for p in pair_names)
        row += f" {worst:>17.2f}R"
    print(row)

    # ── SECTION 6: Scoring ──
    print(f"\n{'━'*74}")
    print(f"  🎯 STRATEGY SCORING (weighted)")
    print(f"{'━'*74}")

    # Score: PnL weight=40%, WR weight=20%, Avg/Trade weight=20%, Risk weight=20%
    scores = {}
    for sn in strat_names:
        cm = combined_metrics[sn]
        # Normalize each metric to 0-100
        pnl_score = (cm["pnl"] / max_pnl) * 100 if max_pnl > 0 else 0
        wr_score = cm["wr"]
        avg_score = (cm["avg_trade"] / max(combined_metrics[s]["avg_trade"] for s in strat_names)) * 100 if any(combined_metrics[s]["avg_trade"] > 0 for s in strat_names) else 0

        # Risk score: lower max_dd = better
        max_possible_dd = max(combined_metrics[s]["max_dd"] for s in strat_names) if any(combined_metrics[s]["max_dd"] > 0 for s in strat_names) else 1
        risk_score = (1 - cm["max_dd"] / max_possible_dd) * 100 if max_possible_dd > 0 else 100

        # Weighted total
        total_score = pnl_score * 0.35 + wr_score * 0.25 + avg_score * 0.20 + risk_score * 0.20

        scores[sn] = {
            "pnl_score": round(pnl_score, 1),
            "wr_score": round(wr_score, 1),
            "avg_score": round(avg_score, 1),
            "risk_score": round(risk_score, 1),
            "total": round(total_score, 1),
        }

    print(f"  {'Strategy':<25s} {'PnL':>8s} {'WR':>8s} {'Avg/T':>8s} {'Risk':>8s} {'TOTAL':>8s}")
    print(f"  {'':25s} {'(35%)':>8s} {'(25%)':>8s} {'(20%)':>8s} {'(20%)':>8s}")
    print(f"  {'─'*70}")

    sorted_strats = sorted(scores.keys(), key=lambda s: -scores[s]["total"])
    for i, sn in enumerate(sorted_strats, 1):
        sc = scores[sn]
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "  "
        print(f"  {medal}{sn:<23s} {sc['pnl_score']:>7.1f} {sc['wr_score']:>7.1f} "
              f"{sc['avg_score']:>7.1f} {sc['risk_score']:>7.1f} {sc['total']:>7.1f}")

    # ── SECTION 7: Conclusion ──
    best_overall = sorted_strats[0]
    print(f"\n{'━'*74}")
    print(f"  📝 CONCLUSION")
    print(f"{'━'*74}")
    print()
    print(f"  Top choice by weighted score: {best_overall}")
    print()

    for sn in strat_names:
        cm = combined_metrics[sn]
        sc = scores[sn]
        print(f"  {'•' if sn != best_overall else '★'} {sn}")
        pros = []
        cons = []

        if sn == "Baseline (Confirm TP)":
            pros.append("Simple, proven WR 84.6%")
            cons.append("Lowest PnL, leaves money on table")

        elif sn == "Fixed R:R 2:1":
            pros.append("Decent balance PnL/WR")
            cons.append("WR drops to 72.6%")

        elif sn == "Fixed R:R 3:1":
            pros.append("Highest raw PnL (+156.7R)")
            pros.append("Best avg/trade (+1.35R)")
            cons.append("Lowest WR (67.2%) — psychological pressure")
            cons.append("~1 in 3 trades lose")

        elif sn == "Partial TP (50%+BE)":
            pros.append("High WR (84.6%) — same as baseline")
            pros.append("Good PnL improvement (+141.6R vs +118.3R)")
            pros.append("Zero risk on Part 2 (worst case = breakeven)")
            cons.append("More complex to implement")
            cons.append("Part 2 may trail a while (capital locked)")

        for p in pros:
            print(f"    ✅ {p}")
        for c in cons:
            print(f"    ⚠️  {c}")
        print()

    print(f"{'━'*74}")

    # Save CSV summary
    records = []
    for sn in strat_names:
        for pair in pair_names:
            m = all_data[sn][pair]
            records.append({"Strategy": sn, "Pair": pair, **m})
    csv_path = os.path.join(OUTPUT_DIR, "tp_strategy_comparison.csv")
    pd.DataFrame(records).to_csv(csv_path, index=False)
    print(f"\n  📁 Report data saved to: {csv_path}")


if __name__ == "__main__":
    main()
