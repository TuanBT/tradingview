"""
backtest_tp_strategies.py — So sánh tất cả chiến lược TP

Strategies:
1. Baseline: 100% close at TP = Confirm Break H/L
2. Baseline + MinRR=0.5: Filter out R:R < 0.5
3. Fixed R:R 1.5:1
4. Fixed R:R 2:1
5. Fixed R:R 3:1
6. Partial TP: 50% at TP1 (Confirm), 50% trail with SL=Entry (BE)
7. Partial TP + MinRR=0.5
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
import numpy as np
from strategy_mst_medio import run_mst_medio, Signal
from backtest_partial_tp import simulate_partial_tp, PartialResult, load_data
from typing import List, Dict

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

PAIRS = [
    ("XAUUSD", "XAUUSD_M5.csv"),
    ("EURUSD", "EURUSD_M5.csv"),
    ("USDJPY", "USDJPY_M5.csv"),
    ("BTCUSD", "BTCUSD_M5.csv"),
]


def run_baseline(signals: List[Signal]) -> Dict:
    """Standard: 100% at TP1 = Confirm Break H/L."""
    closed = [s for s in signals if s.result in ("TP", "SL", "CLOSE_REVERSE")]
    total = len(closed)
    if total == 0:
        return {"trades": 0, "wins": 0, "wr": 0, "pnl": 0, "avg": 0}
    wins = sum(1 for s in closed if s.pnl_r > 0)
    pnl = sum(s.pnl_r for s in closed)
    return {
        "trades": total,
        "wins": wins,
        "wr": round(wins / total * 100, 1),
        "pnl": round(pnl, 2),
        "avg": round(pnl / total, 2),
    }


def run_partial(signals: List[Signal], df: pd.DataFrame) -> Dict:
    """Partial TP: 50% at TP1, 50% with BE stop."""
    results = simulate_partial_tp(signals, df)
    total = len(results)
    if total == 0:
        return {"trades": 0, "wins": 0, "wr": 0, "pnl": 0, "avg": 0}
    wins = sum(1 for r in results if r.total_pnl_r > 0)
    pnl = sum(r.total_pnl_r for r in results)
    return {
        "trades": total,
        "wins": wins,
        "wr": round(wins / total * 100, 1),
        "pnl": round(pnl, 2),
        "avg": round(pnl / total, 2),
    }


def main():
    # Strategy configs
    strategies = [
        ("1. Confirm TP (baseline)", {"tp_mode": "confirm", "min_rr": 0.0, "partial": False}),
        ("2. Confirm TP + MinRR≥0.5", {"tp_mode": "confirm", "min_rr": 0.5, "partial": False}),
        ("3. Confirm TP + MinRR≥1.0", {"tp_mode": "confirm", "min_rr": 1.0, "partial": False}),
        ("4. Fixed R:R 1.5:1", {"tp_mode": "fixed_rr", "fixed_rr": 1.5, "min_rr": 0.0, "partial": False}),
        ("5. Fixed R:R 2:1", {"tp_mode": "fixed_rr", "fixed_rr": 2.0, "min_rr": 0.0, "partial": False}),
        ("6. Fixed R:R 3:1", {"tp_mode": "fixed_rr", "fixed_rr": 3.0, "min_rr": 0.0, "partial": False}),
        ("7. Partial TP (50%+BE)", {"tp_mode": "confirm", "min_rr": 0.0, "partial": True}),
        ("8. Partial TP + MinRR≥0.5", {"tp_mode": "confirm", "min_rr": 0.5, "partial": True}),
    ]

    # Results storage: strategy_name -> pair -> metrics
    all_results: Dict[str, Dict[str, Dict]] = {}

    for pair_name, data_file in PAIRS:
        path = os.path.join(DATA_DIR, data_file)
        if not os.path.exists(path):
            continue

        df = load_data(path)
        print(f"Loading {pair_name}: {len(df)} bars")

        for strat_name, config in strategies:
            tp_mode = config.get("tp_mode", "confirm")
            fixed_rr = config.get("fixed_rr", 2.0)
            min_rr = config.get("min_rr", 0.0)
            partial = config.get("partial", False)

            signals, _ = run_mst_medio(
                df,
                pivot_len=5,
                break_mult=0.25,
                impulse_mult=1.5,
                tp_mode=tp_mode,
                fixed_rr=fixed_rr,
                min_rr=min_rr,
                debug=False,
            )

            if partial:
                metrics = run_partial(signals, df)
            else:
                metrics = run_baseline(signals)

            if strat_name not in all_results:
                all_results[strat_name] = {}
            all_results[strat_name][pair_name] = metrics

    # ══════════════════════════════════════════════════════════════
    # PRINT RESULTS
    # ══════════════════════════════════════════════════════════════
    pair_names = [p[0] for p in PAIRS if os.path.exists(os.path.join(DATA_DIR, p[1]))]

    # ── Per-pair table ──
    for pair in pair_names:
        print(f"\n{'═'*80}")
        print(f"  {pair}")
        print(f"{'═'*80}")
        print(f"  {'Strategy':<30s} {'Trades':>7s} {'WR':>7s} {'PnL(R)':>10s} {'Avg/Trade':>10s}")
        print(f"  {'─'*66}")

        best_pnl = -999
        best_strat = ""

        for strat_name, _ in strategies:
            m = all_results.get(strat_name, {}).get(pair, {})
            if not m or m["trades"] == 0:
                continue
            if m["pnl"] > best_pnl:
                best_pnl = m["pnl"]
                best_strat = strat_name
            print(f"  {strat_name:<30s} {m['trades']:>7d} {m['wr']:>6.1f}% {m['pnl']:>+9.2f}R {m['avg']:>+9.2f}R")

        print(f"  {'─'*66}")
        print(f"  🏆 Best: {best_strat} ({best_pnl:+.2f}R)")

    # ── Combined table ──
    print(f"\n\n{'═'*80}")
    print(f"  COMBINED — ALL PAIRS")
    print(f"{'═'*80}")
    print(f"  {'Strategy':<30s} {'Trades':>7s} {'WR':>7s} {'PnL(R)':>10s} {'Avg/Trade':>10s}")
    print(f"  {'─'*66}")

    best_pnl = -999
    best_strat = ""

    for strat_name, _ in strategies:
        total_trades = 0
        total_wins = 0
        total_pnl = 0.0

        for pair in pair_names:
            m = all_results.get(strat_name, {}).get(pair, {})
            if not m:
                continue
            total_trades += m["trades"]
            total_wins += m["wins"]
            total_pnl += m["pnl"]

        if total_trades == 0:
            continue

        wr = round(total_wins / total_trades * 100, 1)
        avg = round(total_pnl / total_trades, 2)

        if total_pnl > best_pnl:
            best_pnl = total_pnl
            best_strat = strat_name

        marker = ""
        print(f"  {strat_name:<30s} {total_trades:>7d} {wr:>6.1f}% {total_pnl:>+9.2f}R {avg:>+9.2f}R")

    print(f"  {'─'*66}")
    print(f"  🏆 Best overall: {best_strat} ({best_pnl:+.2f}R)")

    # ── Summary recommendation ──
    print(f"\n{'═'*80}")
    print(f"  📋 SUMMARY & RECOMMENDATIONS")
    print(f"{'═'*80}")

    # Find rankings
    rankings = []
    for strat_name, _ in strategies:
        total_pnl = sum(
            all_results.get(strat_name, {}).get(pair, {}).get("pnl", 0)
            for pair in pair_names
        )
        total_trades = sum(
            all_results.get(strat_name, {}).get(pair, {}).get("trades", 0)
            for pair in pair_names
        )
        if total_trades > 0:
            rankings.append((strat_name, total_pnl, total_trades))

    rankings.sort(key=lambda x: -x[1])

    print(f"\n  Ranking by Total PnL:")
    for i, (name, pnl, trades) in enumerate(rankings, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "  "
        print(f"  {medal} #{i}: {name:<30s} {pnl:>+9.2f}R ({trades} trades)")


if __name__ == "__main__":
    main()
