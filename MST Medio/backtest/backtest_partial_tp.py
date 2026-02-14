"""
backtest_partial_tp.py — Compare Full TP vs Partial TP (50/50)
Partial: Part1=TP at Confirm H/L, Part2=Hold until next opposite signal
After TP1 hit → SL moves to breakeven
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from dataclasses import dataclass
from typing import List, Optional
from strategy_mst_medio import run_mst_medio, Signal

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


@dataclass
class PartialTrade:
    signal: Signal
    part1_pnl_r: float = 0.0
    part2_pnl_r: float = 0.0
    part1_result: str = ""    # TP, SL
    part2_result: str = ""    # TP_OPP (next opposite), SL, BE, OPEN


def simulate_partial_tp(df: pd.DataFrame, signals: List[Signal]) -> List[PartialTrade]:
    """
    Part1 (50%): Close at TP (confirm candle H/L) — same as current
    Part2 (50%): Hold until next OPPOSITE direction signal → close at that bar's close
      - After TP1 hit → move Part2 SL to entry (breakeven)
      - If SL hit before TP1 → both parts = -1R
      - If Part2 SL (breakeven) hit → Part2 = 0R
    """
    times = df.index.values
    highs = df["High"].values
    lows = df["Low"].values
    closes = df["Close"].values

    time_to_idx = {}
    for i, t in enumerate(times):
        time_to_idx[t] = i

    trades: List[PartialTrade] = []

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

        # Find next opposite signal confirm time
        next_opp_confirm_idx = None
        for future_sig in signals[sig_idx + 1:]:
            if future_sig.direction != sig.direction:
                idx = time_to_idx.get(future_sig.confirm_time)
                if idx is not None:
                    next_opp_confirm_idx = idx
                break

        part1_done = False
        part2_done = False
        part2_sl = sig.sl  # Initially same as original SL

        for bar_i in range(confirm_idx + 1, len(times)):
            bar_h = highs[bar_i]
            bar_l = lows[bar_i]
            bar_c = closes[bar_i]

            # ── Part1: TP/SL check ──
            if not part1_done:
                if sig.direction == "BUY":
                    if bar_l <= sig.sl:
                        # SL hit → both parts lose
                        pt.part1_pnl_r = -1.0
                        pt.part1_result = "SL"
                        pt.part2_pnl_r = -1.0
                        pt.part2_result = "SL"
                        part1_done = part2_done = True
                        break
                    if sig.tp > 0 and bar_h >= sig.tp:
                        rr = abs(sig.tp - sig.entry) / risk
                        pt.part1_pnl_r = rr
                        pt.part1_result = "TP"
                        part1_done = True
                        part2_sl = sig.entry  # Move SL to breakeven
                else:  # SELL
                    if bar_h >= sig.sl:
                        pt.part1_pnl_r = -1.0
                        pt.part1_result = "SL"
                        pt.part2_pnl_r = -1.0
                        pt.part2_result = "SL"
                        part1_done = part2_done = True
                        break
                    if sig.tp > 0 and bar_l <= sig.tp:
                        rr = abs(sig.entry - sig.tp) / risk
                        pt.part1_pnl_r = rr
                        pt.part1_result = "TP"
                        part1_done = True
                        part2_sl = sig.entry

            # ── Part2: SL or next opposite signal ──
            if part1_done and not part2_done:
                # Check Part2 SL (breakeven)
                if sig.direction == "BUY":
                    if bar_l <= part2_sl:
                        if part2_sl >= sig.entry:
                            pt.part2_pnl_r = 0.0
                            pt.part2_result = "BE"
                        else:
                            pt.part2_pnl_r = (part2_sl - sig.entry) / risk
                            pt.part2_result = "SL"
                        part2_done = True
                        break
                else:
                    if bar_h >= part2_sl:
                        if part2_sl <= sig.entry:
                            pt.part2_pnl_r = 0.0
                            pt.part2_result = "BE"
                        else:
                            pt.part2_pnl_r = (sig.entry - part2_sl) / risk
                            pt.part2_result = "SL"
                        part2_done = True
                        break

                # Check if next opposite signal fires
                if next_opp_confirm_idx is not None and bar_i >= next_opp_confirm_idx:
                    if sig.direction == "BUY":
                        pt.part2_pnl_r = (bar_c - sig.entry) / risk
                    else:
                        pt.part2_pnl_r = (sig.entry - bar_c) / risk
                    pt.part2_result = "OPP"
                    part2_done = True
                    break

        # Handle unclosed parts at end of data
        if not part1_done:
            last_c = closes[-1]
            if sig.direction == "BUY":
                pt.part1_pnl_r = (last_c - sig.entry) / risk
            else:
                pt.part1_pnl_r = (sig.entry - last_c) / risk
            pt.part1_result = "OPEN"
            pt.part2_pnl_r = pt.part1_pnl_r
            pt.part2_result = "OPEN"

        if not part2_done and part1_done:
            last_c = closes[-1]
            if sig.direction == "BUY":
                pt.part2_pnl_r = (last_c - sig.entry) / risk
            else:
                pt.part2_pnl_r = (sig.entry - last_c) / risk
            pt.part2_result = "OPEN"

        trades.append(pt)

    return trades


def print_results(trades: List[PartialTrade], label: str):
    n = len(trades)
    if n == 0:
        print(f"\n{label}: No trades")
        return

    # Full TP (original)
    full_pnl = sum(t.signal.pnl_r for t in trades)
    full_wins = sum(1 for t in trades if t.signal.result == "TP")
    full_wr = full_wins / n * 100

    # Partial TP: average of both parts (each is 50%)
    partial_pnl = sum((t.part1_pnl_r + t.part2_pnl_r) / 2 for t in trades)

    # Part2 stats
    p2_tp_opp = sum(1 for t in trades if t.part2_result == "OPP")
    p2_be = sum(1 for t in trades if t.part2_result == "BE")
    p2_sl = sum(1 for t in trades if t.part2_result == "SL")
    p2_open = sum(1 for t in trades if t.part2_result == "OPEN")
    p2_pnl_avg = sum(t.part2_pnl_r for t in trades) / n

    print(f"\n{'─' * 60}")
    print(f"  {label} — {n} trades")
    print(f"{'─' * 60}")
    print(f"  Full TP:    WR={full_wr:.1f}% | PnL={full_pnl:+.2f}R | Avg={full_pnl/n:+.2f}R")
    print(f"  Partial TP: PnL={partial_pnl:+.2f}R | Avg={partial_pnl/n:+.2f}R")
    print(f"  Part2 exits: OPP={p2_tp_opp} BE={p2_be} SL={p2_sl} OPEN={p2_open} | Avg Part2={p2_pnl_avg:+.2f}R")
    diff = partial_pnl - full_pnl
    print(f"  Diff: {diff:+.2f}R {'✅ PARTIAL BETTER' if diff > 0 else '❌ FULL BETTER'}")

    # Show detailed Part2 results
    print(f"\n  Top Part2 profits:")
    sorted_by_p2 = sorted(trades, key=lambda t: t.part2_pnl_r, reverse=True)
    for t in sorted_by_p2[:5]:
        print(f"    {t.signal.direction:>4} {str(t.signal.confirm_time):>22} "
              f"Part1={t.part1_pnl_r:+.2f}R Part2={t.part2_pnl_r:+.2f}R ({t.part2_result})")
    print(f"  Worst Part2:")
    for t in sorted_by_p2[-3:]:
        print(f"    {t.signal.direction:>4} {str(t.signal.confirm_time):>22} "
              f"Part1={t.part1_pnl_r:+.2f}R Part2={t.part2_pnl_r:+.2f}R ({t.part2_result})")


def load_data(path: str) -> pd.DataFrame:
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

    print("=" * 60)
    print("MST Medio v2.0 — Full TP vs Partial TP (50/50)")
    print("Part1: TP at Confirm H/L")
    print("Part2: Hold → close at next opposite signal")
    print("After TP1 → SL moves to breakeven")
    print("=" * 60)

    results = []

    for symbol, filename in PAIRS:
        filepath = os.path.join(DATA_DIR, filename)
        if not os.path.exists(filepath):
            print(f"\n⚠️ {symbol}: No data file ({filename})")
            continue

        df = load_data(filepath)

        signals, _ = run_mst_medio(df, pivot_len=5, break_mult=0.25, impulse_mult=1.5,
                                     min_rr=0, tp_mode="confirm", debug=False)
        if not signals:
            print(f"\n{symbol}: No signals")
            continue

        trades = simulate_partial_tp(df, signals)
        print_results(trades, f"{symbol} M5")

        n = len(trades)
        full_pnl = sum(t.signal.pnl_r for t in trades)
        partial_pnl = sum((t.part1_pnl_r + t.part2_pnl_r) / 2 for t in trades)
        results.append((symbol, n, full_pnl, partial_pnl))

    # Summary
    print(f"\n\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    print(f"{'Symbol':<15} {'N':>4} {'Full TP(R)':>11} {'Partial(R)':>11} {'Diff':>10}")
    print("-" * 55)
    tf = tp = 0
    for sym, n, fp, pp in results:
        diff = pp - fp
        print(f"{sym:<15} {n:>4} {fp:>+10.2f} {pp:>+10.2f} {diff:>+9.2f}")
        tf += fp
        tp += pp
    print("-" * 55)
    td = tp - tf
    print(f"{'TOTAL':<15} {'':>4} {tf:>+10.2f} {tp:>+10.2f} {td:>+9.2f} {'✅' if td > 0 else '❌'}")


if __name__ == "__main__":
    main()
