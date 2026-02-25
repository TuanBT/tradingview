"""
backtest_partial_compare.py — Compare 2 Partial TP modes
Mode A (current): Part2 SL = SL gốc → move to BE after Part1 TP
Mode B (new):     Part2 SL = Entry (BE) from start → Part2 is risk-free immediately
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from dataclasses import dataclass
from typing import List
from strategy_mst_medio import run_mst_medio, Signal

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


@dataclass
class PartialTrade:
    signal: Signal
    part1_pnl_r: float = 0.0
    part2_pnl_r: float = 0.0
    part1_result: str = ""
    part2_result: str = ""


def simulate_partial(df, signals, mode="A"):
    """
    Mode A: Part2 SL = SL gốc → move to BE after Part1 TP
    Mode B: Part2 SL = entry (BE) from start
    """
    times = df.index.values
    highs = df["High"].values
    lows = df["Low"].values
    closes = df["Close"].values

    time_to_idx = {}
    for i, t in enumerate(times):
        time_to_idx[t] = i

    trades = []

    for sig_idx, sig in enumerate(signals):
        pt = PartialTrade(signal=sig)

        confirm_idx = time_to_idx.get(sig.confirm_time)
        if confirm_idx is None:
            pt.part1_pnl_r = sig.pnl_r
            pt.part2_pnl_r = sig.pnl_r
            pt.part1_result = sig.result
            pt.part2_result = sig.result
            trades.append(pt)
            continue

        risk = abs(sig.entry - sig.sl)
        if risk == 0:
            trades.append(pt)
            continue

        # Next opposite signal
        next_opp_idx = None
        for future_sig in signals[sig_idx + 1:]:
            if future_sig.direction != sig.direction:
                idx = time_to_idx.get(future_sig.confirm_time)
                if idx is not None:
                    next_opp_idx = idx
                break

        part1_done = False
        part2_done = False

        if mode == "A":
            # Mode A: Part2 starts with SL gốc, changes to BE after Part1 TP
            part2_sl = sig.sl
        else:
            # Mode B: Part2 starts with SL = entry (BE) from the start
            part2_sl = sig.entry

        for bar_i in range(confirm_idx + 1, len(times)):
            bar_h = highs[bar_i]
            bar_l = lows[bar_i]
            bar_c = closes[bar_i]

            if sig.direction == "BUY":
                # ── Part1 ──
                if not part1_done:
                    if bar_l <= sig.sl:
                        # SL hit on Part1
                        pt.part1_pnl_r = -1.0
                        pt.part1_result = "SL"
                        part1_done = True
                        if mode == "A":
                            # Mode A: Part2 also SL (same SL)
                            pt.part2_pnl_r = -1.0
                            pt.part2_result = "SL"
                            part2_done = True
                            break
                        # Mode B: Part2 has separate SL at entry
                        # Check if Part2 SL (entry) is also hit
                        if not part2_done and bar_l <= part2_sl:
                            pt.part2_pnl_r = 0.0
                            pt.part2_result = "BE"
                            part2_done = True
                            break
                    elif sig.tp > 0 and bar_h >= sig.tp:
                        rr = abs(sig.tp - sig.entry) / risk
                        pt.part1_pnl_r = rr
                        pt.part1_result = "TP"
                        part1_done = True
                        if mode == "A":
                            part2_sl = sig.entry  # Move to BE

                # ── Part2 (BUY) ──
                if not part2_done:
                    if bar_l <= part2_sl:
                        if part2_sl >= sig.entry:
                            pt.part2_pnl_r = 0.0
                            pt.part2_result = "BE"
                        else:
                            pt.part2_pnl_r = (part2_sl - sig.entry) / risk
                            pt.part2_result = "SL"
                        part2_done = True
                        if part1_done:
                            break
                    elif next_opp_idx is not None and bar_i >= next_opp_idx:
                        pt.part2_pnl_r = (bar_c - sig.entry) / risk
                        pt.part2_result = "OPP"
                        part2_done = True
                        if part1_done:
                            break

            else:  # SELL
                # ── Part1 ──
                if not part1_done:
                    if bar_h >= sig.sl:
                        pt.part1_pnl_r = -1.0
                        pt.part1_result = "SL"
                        part1_done = True
                        if mode == "A":
                            pt.part2_pnl_r = -1.0
                            pt.part2_result = "SL"
                            part2_done = True
                            break
                        if not part2_done and bar_h >= part2_sl:
                            pt.part2_pnl_r = 0.0
                            pt.part2_result = "BE"
                            part2_done = True
                            break
                    elif sig.tp > 0 and bar_l <= sig.tp:
                        rr = abs(sig.entry - sig.tp) / risk
                        pt.part1_pnl_r = rr
                        pt.part1_result = "TP"
                        part1_done = True
                        if mode == "A":
                            part2_sl = sig.entry

                # ── Part2 (SELL) ──
                if not part2_done:
                    if bar_h >= part2_sl:
                        if part2_sl <= sig.entry:
                            pt.part2_pnl_r = 0.0
                            pt.part2_result = "BE"
                        else:
                            pt.part2_pnl_r = (sig.entry - part2_sl) / risk
                            pt.part2_result = "SL"
                        part2_done = True
                        if part1_done:
                            break
                    elif next_opp_idx is not None and bar_i >= next_opp_idx:
                        pt.part2_pnl_r = (sig.entry - bar_c) / risk
                        pt.part2_result = "OPP"
                        part2_done = True
                        if part1_done:
                            break

            if part1_done and part2_done:
                break

        # Handle unclosed at end
        if not part1_done:
            last_c = closes[-1]
            if sig.direction == "BUY":
                pt.part1_pnl_r = (last_c - sig.entry) / risk
            else:
                pt.part1_pnl_r = (sig.entry - last_c) / risk
            pt.part1_result = "OPEN"
        if not part2_done:
            last_c = closes[-1]
            if sig.direction == "BUY":
                pt.part2_pnl_r = (last_c - sig.entry) / risk
            else:
                pt.part2_pnl_r = (sig.entry - last_c) / risk
            pt.part2_result = "OPEN"

        trades.append(pt)

    return trades


def calc_stats(trades, label):
    n = len(trades)
    if n == 0:
        return None

    pnl = sum((t.part1_pnl_r + t.part2_pnl_r) / 2 for t in trades)
    wins = sum(1 for t in trades if (t.part1_pnl_r + t.part2_pnl_r) > 0)
    wr = wins / n * 100

    p2_be = sum(1 for t in trades if t.part2_result == "BE")
    p2_sl = sum(1 for t in trades if t.part2_result == "SL")
    p2_opp = sum(1 for t in trades if t.part2_result == "OPP")
    p2_open = sum(1 for t in trades if t.part2_result == "OPEN")

    return {
        "label": label, "n": n, "pnl": pnl, "wr": wr, "wins": wins,
        "p2_be": p2_be, "p2_sl": p2_sl, "p2_opp": p2_opp, "p2_open": p2_open,
    }


def load_data(path):
    df = pd.read_csv(path, parse_dates=["datetime"])
    df.set_index("datetime", inplace=True)
    df.sort_index(inplace=True)
    for cu, cl in [("Open","open"),("High","high"),("Low","low"),("Close","close"),("Volume","volume")]:
        if cu in df.columns and cl in df.columns:
            df[cu] = df[cu].fillna(df[cl])
            df.drop(columns=[cl], inplace=True, errors="ignore")
    df.drop(columns=["symbol"], inplace=True, errors="ignore")
    df.dropna(subset=["Open","High","Low","Close"], inplace=True)
    df = df[df.index.dayofweek < 5]
    return df


def main():
    PAIRS = [
        ("XAUUSD",        "XAUUSD_M5.csv"),
        ("BTCUSD",        "BTCUSD_M5.csv"),
        ("USOILUSDT.P",   "USOIL_M5.csv"),
        ("EURUSD",        "EURUSD_M5.csv"),
        ("USDJPY",        "USDJPY_M5.csv"),
    ]

    print("=" * 80)
    print("MST Medio v2.0 — Partial TP Mode Comparison")
    print("=" * 80)
    print("Mode A (current): Part2 SL = SL goc -> move to BE after Part1 TP")
    print("Mode B (new):     Part2 SL = Entry (BE) from start -> risk-free Part2")
    print("=" * 80)

    all_a = []
    all_b = []

    for symbol, filename in PAIRS:
        filepath = os.path.join(DATA_DIR, filename)
        if not os.path.exists(filepath):
            print(f"\n  {symbol}: No data file")
            continue

        df = load_data(filepath)
        signals, _ = run_mst_medio(df, pivot_len=5, break_mult=0.25, impulse_mult=1.5,
                                     min_rr=0, tp_mode="confirm")
        if not signals:
            print(f"\n  {symbol}: No signals")
            continue

        trades_a = simulate_partial(df, signals, mode="A")
        trades_b = simulate_partial(df, signals, mode="B")

        sa = calc_stats(trades_a, f"{symbol} Mode A")
        sb = calc_stats(trades_b, f"{symbol} Mode B")

        if sa and sb:
            all_a.append((symbol, sa))
            all_b.append((symbol, sb))

            diff = sb["pnl"] - sa["pnl"]
            winner = "B" if diff > 0 else "A"
            print(f"\n  {symbol} ({sa['n']} trades):")
            print(f"    Mode A: WR={sa['wr']:.1f}% PnL={sa['pnl']:+.2f}R | P2: BE={sa['p2_be']} SL={sa['p2_sl']} OPP={sa['p2_opp']}")
            print(f"    Mode B: WR={sb['wr']:.1f}% PnL={sb['pnl']:+.2f}R | P2: BE={sb['p2_be']} SL={sb['p2_sl']} OPP={sb['p2_opp']}")
            print(f"    Diff: {diff:+.2f}R -> Mode {winner} better")

    # Summary
    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print(f"{'=' * 80}")
    print(f"{'Symbol':<15} {'N':>4} {'A WR%':>7} {'A PnL':>8} {'B WR%':>7} {'B PnL':>8} {'Diff':>8} {'Winner':>8}")
    print("-" * 70)

    ta_pnl = tb_pnl = 0
    ta_w = tb_w = 0
    tn = 0
    for (sym, sa), (_, sb) in zip(all_a, all_b):
        d = sb["pnl"] - sa["pnl"]
        w = "B" if d > 0 else "A"
        print(f"{sym:<15} {sa['n']:>4} {sa['wr']:>6.1f}% {sa['pnl']:>+7.2f} {sb['wr']:>6.1f}% {sb['pnl']:>+7.2f} {d:>+7.2f} {'<- '+w:>8}")
        ta_pnl += sa["pnl"]; tb_pnl += sb["pnl"]
        ta_w += sa["wins"]; tb_w += sb["wins"]
        tn += sa["n"]
    print("-" * 70)
    td = tb_pnl - ta_pnl
    awr = ta_w / tn * 100 if tn > 0 else 0
    bwr = tb_w / tn * 100 if tn > 0 else 0
    tw = "B" if td > 0 else "A"
    print(f"{'TOTAL':<15} {tn:>4} {awr:>6.1f}% {ta_pnl:>+7.2f} {bwr:>6.1f}% {tb_pnl:>+7.2f} {td:>+7.2f} {'<- '+tw:>8}")

    print(f"\nConclusion: Mode {tw} is overall better by {abs(td):.2f}R")


if __name__ == "__main__":
    main()
