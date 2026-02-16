"""
backtest_htf_filter.py — Compare WITH vs WITHOUT HTF Trend Filter
HTF Filter: H1 EMA50 — BUY only when price > EMA, SELL only when price < EMA

Combines with Partial TP to show full picture:
  - No Filter + Full TP
  - No Filter + Partial TP
  - HTF Filter + Full TP
  - HTF Filter + Partial TP
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
import numpy as np
from typing import List
from strategy_mst_medio import run_mst_medio, Signal, print_summary
from backtest_partial_tp import simulate_partial_tp, load_data

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

# HTF Filter settings
HTF_EMA_LEN = 50
HTF_TIMEFRAME = "H1"   # Resample M5 → H1


def calc_htf_ema(df_m5: pd.DataFrame, ema_len: int = 50) -> pd.Series:
    """
    Resample M5 data to H1 and calculate EMA.
    Returns a Series indexed by H1 bar open time with EMA values.
    """
    # Resample to H1 OHLC
    df_h1 = df_m5.resample("1h").agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
    }).dropna()

    # Calculate EMA on H1 close
    ema = df_h1["Close"].ewm(span=ema_len, adjust=False).mean()
    return ema


def get_htf_ema_at_time(ema_h1: pd.Series, signal_time: pd.Timestamp) -> float:
    """
    Get the H1 EMA value at the time of a signal.
    Uses the most recent completed H1 bar (not the current forming bar).
    """
    # Floor to H1 boundary
    h1_time = signal_time.floor("1h")
    # Use previous completed H1 bar (not current forming one)
    prev_h1 = h1_time - pd.Timedelta(hours=1)

    # Find closest available EMA value <= prev_h1
    valid = ema_h1[ema_h1.index <= prev_h1]
    if valid.empty:
        return np.nan
    return valid.iloc[-1]


def apply_htf_filter(signals: List[Signal], df_m5: pd.DataFrame,
                      ema_len: int = 50, debug: bool = False) -> List[Signal]:
    """
    Filter signals using HTF EMA trend.
    BUY only when close > EMA(H1), SELL only when close < EMA(H1).
    """
    ema_h1 = calc_htf_ema(df_m5, ema_len)
    filtered = []
    skipped_buy = 0
    skipped_sell = 0

    for sig in signals:
        ema_val = get_htf_ema_at_time(ema_h1, sig.confirm_time)
        if np.isnan(ema_val):
            # No EMA data yet (early bars) → allow signal (fail-open)
            filtered.append(sig)
            continue

        # Use the signal's confirm bar close (approximate: entry is the old SH/SL)
        # In EA, we use iClose(_Symbol, _Period, 1) at confirm time
        # Here we use the confirm bar's close from M5 data
        confirm_close = df_m5.loc[sig.confirm_time, "Close"] if sig.confirm_time in df_m5.index else sig.entry

        if sig.direction == "BUY" and confirm_close < ema_val:
            skipped_buy += 1
            if debug:
                print(f"  ⚠️ HTF: BUY skipped @ {sig.confirm_time} — "
                      f"Close={confirm_close:.2f} < EMA{ema_len}={ema_val:.2f}")
            continue

        if sig.direction == "SELL" and confirm_close > ema_val:
            skipped_sell += 1
            if debug:
                print(f"  ⚠️ HTF: SELL skipped @ {sig.confirm_time} — "
                      f"Close={confirm_close:.2f} > EMA{ema_len}={ema_val:.2f}")
            continue

        filtered.append(sig)

    if debug:
        print(f"  HTF Filter: {len(signals)}→{len(filtered)} signals "
              f"(skipped {skipped_buy} BUY, {skipped_sell} SELL)")

    return filtered


def calc_stats(signals: List[Signal]):
    """Calculate basic stats from signals."""
    closed = [s for s in signals if s.result in ("TP", "SL", "CLOSE_REVERSE")]
    n = len(closed)
    if n == 0:
        return 0, 0, 0.0, 0.0
    wins = sum(1 for s in closed if s.pnl_r > 0)
    wr = wins / n * 100
    total_r = sum(s.pnl_r for s in closed)
    return n, wins, wr, total_r


def calc_partial_stats(trades):
    """Calculate partial TP stats."""
    n = len(trades)
    if n == 0:
        return 0, 0, 0.0, 0.0
    pnl = sum((t.part1_pnl_r + t.part2_pnl_r) / 2 for t in trades)
    wins = sum(1 for t in trades if (t.part1_pnl_r + t.part2_pnl_r) > 0)
    wr = wins / n * 100
    return n, wins, wr, pnl


def main():
    PAIRS = [
        ("XAUUSD",        "XAUUSD_M5.csv"),
        ("BTCUSD",        "BTCUSD_M5.csv"),
        ("USOIL",         "USOIL_M5.csv"),
        ("EURUSD",        "EURUSD_M5.csv"),
        ("USDJPY",        "USDJPY_M5.csv"),
    ]

    print("=" * 75)
    print("MST Medio v2.0 — HTF Trend Filter Backtest")
    print(f"Filter: EMA{HTF_EMA_LEN} on {HTF_TIMEFRAME}")
    print("BUY only when Close > EMA, SELL only when Close < EMA")
    print("=" * 75)

    # Collect results per pair
    all_results = []

    for symbol, filename in PAIRS:
        filepath = os.path.join(DATA_DIR, filename)
        if not os.path.exists(filepath):
            print(f"\n⚠️ {symbol}: No data file ({filename})")
            continue

        df = load_data(filepath)
        print(f"\n{'─' * 75}")
        print(f"  {symbol} M5 | {len(df)} bars | {df.index[0]} → {df.index[-1]}")
        print(f"{'─' * 75}")

        # Generate signals (no filter)
        signals_all, _ = run_mst_medio(df, pivot_len=5, break_mult=0.25, impulse_mult=1.5,
                                         min_rr=0, tp_mode="confirm", debug=False)

        if not signals_all:
            print(f"  No signals")
            continue

        # Apply HTF filter
        signals_htf = apply_htf_filter(signals_all, df, HTF_EMA_LEN, debug=True)

        # No Filter stats
        n_all, w_all, wr_all, pnl_all = calc_stats(signals_all)
        trades_all = simulate_partial_tp(df, signals_all)
        n_p_all, w_p_all, wr_p_all, pnl_p_all = calc_partial_stats(trades_all)

        # HTF Filter stats
        n_htf, w_htf, wr_htf, pnl_htf = calc_stats(signals_htf)
        trades_htf = simulate_partial_tp(df, signals_htf)
        n_p_htf, w_p_htf, wr_p_htf, pnl_p_htf = calc_partial_stats(trades_htf)

        # Show comparison
        print(f"\n  {'Mode':<25} {'N':>4} {'WR%':>7} {'PnL(R)':>9} {'Avg(R)':>8}")
        print(f"  {'-'*55}")
        avg_all = pnl_all / n_all if n_all > 0 else 0
        avg_p_all = pnl_p_all / n_p_all if n_p_all > 0 else 0
        avg_htf = pnl_htf / n_htf if n_htf > 0 else 0
        avg_p_htf = pnl_p_htf / n_p_htf if n_p_htf > 0 else 0

        print(f"  {'No Filter + Full TP':<25} {n_all:>4} {wr_all:>6.1f}% {pnl_all:>+8.2f} {avg_all:>+7.2f}")
        print(f"  {'No Filter + Partial TP':<25} {n_p_all:>4} {wr_p_all:>6.1f}% {pnl_p_all:>+8.2f} {avg_p_all:>+7.2f}")
        print(f"  {'HTF Filter + Full TP':<25} {n_htf:>4} {wr_htf:>6.1f}% {pnl_htf:>+8.2f} {avg_htf:>+7.2f}")
        print(f"  {'HTF Filter + Partial TP':<25} {n_p_htf:>4} {wr_p_htf:>6.1f}% {pnl_p_htf:>+8.2f} {avg_p_htf:>+7.2f}")

        # Filtered signals detail
        filtered_count = len(signals_all) - len(signals_htf)
        buy_all = sum(1 for s in signals_all if s.direction == "BUY")
        sell_all = sum(1 for s in signals_all if s.direction == "SELL")
        buy_htf = sum(1 for s in signals_htf if s.direction == "BUY")
        sell_htf = sum(1 for s in signals_htf if s.direction == "SELL")
        print(f"\n  Signals: {len(signals_all)} → {len(signals_htf)} ({filtered_count} filtered)")
        print(f"  BUY: {buy_all} → {buy_htf} | SELL: {sell_all} → {sell_htf}")

        # Show which signals were filtered and their outcomes
        filtered_sigs = [s for s in signals_all if s not in signals_htf]
        if filtered_sigs:
            filt_tp = sum(1 for s in filtered_sigs if s.result == "TP")
            filt_sl = sum(1 for s in filtered_sigs if s.result == "SL")
            filt_rev = sum(1 for s in filtered_sigs if s.result == "CLOSE_REVERSE")
            filt_open = sum(1 for s in filtered_sigs if s.result == "OPEN")
            filt_pnl = sum(s.pnl_r for s in filtered_sigs if s.result in ("TP", "SL", "CLOSE_REVERSE"))
            print(f"  Filtered outcomes: TP={filt_tp} SL={filt_sl} Rev={filt_rev} Open={filt_open} | PnL={filt_pnl:+.2f}R")
            if filt_pnl < 0:
                print(f"  ✅ Filter removed NET LOSING trades ({filt_pnl:+.2f}R) → GOOD!")
            elif filt_pnl > 0:
                print(f"  ⚠️ Filter removed NET WINNING trades ({filt_pnl:+.2f}R) → some missed profit")
            else:
                print(f"  ⚖️ Filter removed break-even trades")

        all_results.append({
            "symbol": symbol,
            "n_all": n_all, "wr_all": wr_all, "pnl_all": pnl_all,
            "n_p_all": n_p_all, "wr_p_all": wr_p_all, "pnl_p_all": pnl_p_all,
            "n_htf": n_htf, "wr_htf": wr_htf, "pnl_htf": pnl_htf,
            "n_p_htf": n_p_htf, "wr_p_htf": wr_p_htf, "pnl_p_htf": pnl_p_htf,
            "filtered": len(signals_all) - len(signals_htf),
        })

    # ══════════════════════════════════════════════════════════════
    # GRAND SUMMARY
    # ══════════════════════════════════════════════════════════════
    print(f"\n\n{'═' * 75}")
    print("GRAND SUMMARY — ALL PAIRS")
    print(f"{'═' * 75}")

    header = f"{'Symbol':<10} │ {'No Filter':^22} │ {'HTF Filter':^22} │ {'Diff':>6}"
    print(f"\n  Full TP:")
    print(f"  {header}")
    print(f"  {'─'*70}")
    tn_all = tw_all = tpnl_all = tn_htf = tw_htf = tpnl_htf = 0
    for r in all_results:
        diff = r["pnl_htf"] - r["pnl_all"]
        print(f"  {r['symbol']:<10} │ {r['n_all']:>3}sig {r['wr_all']:>5.1f}% {r['pnl_all']:>+7.2f}R │ "
              f"{r['n_htf']:>3}sig {r['wr_htf']:>5.1f}% {r['pnl_htf']:>+7.2f}R │ {diff:>+6.2f}")
        tn_all += r["n_all"]; tw_all += round(r["n_all"] * r["wr_all"] / 100); tpnl_all += r["pnl_all"]
        tn_htf += r["n_htf"]; tw_htf += round(r["n_htf"] * r["wr_htf"] / 100); tpnl_htf += r["pnl_htf"]

    diff_total = tpnl_htf - tpnl_all
    twr_all = tw_all / tn_all * 100 if tn_all > 0 else 0
    twr_htf = tw_htf / tn_htf * 100 if tn_htf > 0 else 0
    print(f"  {'─'*70}")
    print(f"  {'TOTAL':<10} │ {tn_all:>3}sig {twr_all:>5.1f}% {tpnl_all:>+7.2f}R │ "
          f"{tn_htf:>3}sig {twr_htf:>5.1f}% {tpnl_htf:>+7.2f}R │ {diff_total:>+6.2f}")

    print(f"\n  Partial TP:")
    print(f"  {header}")
    print(f"  {'─'*70}")
    tn_p_all = tw_p_all = tpnl_p_all = tn_p_htf = tw_p_htf = tpnl_p_htf = 0
    for r in all_results:
        diff = r["pnl_p_htf"] - r["pnl_p_all"]
        print(f"  {r['symbol']:<10} │ {r['n_p_all']:>3}sig {r['wr_p_all']:>5.1f}% {r['pnl_p_all']:>+7.2f}R │ "
              f"{r['n_p_htf']:>3}sig {r['wr_p_htf']:>5.1f}% {r['pnl_p_htf']:>+7.2f}R │ {diff:>+6.2f}")
        tn_p_all += r["n_p_all"]; tw_p_all += round(r["n_p_all"] * r["wr_p_all"] / 100); tpnl_p_all += r["pnl_p_all"]
        tn_p_htf += r["n_p_htf"]; tw_p_htf += round(r["n_p_htf"] * r["wr_p_htf"] / 100); tpnl_p_htf += r["pnl_p_htf"]

    diff_p_total = tpnl_p_htf - tpnl_p_all
    twr_p_all = tw_p_all / tn_p_all * 100 if tn_p_all > 0 else 0
    twr_p_htf = tw_p_htf / tn_p_htf * 100 if tn_p_htf > 0 else 0
    print(f"  {'─'*70}")
    print(f"  {'TOTAL':<10} │ {tn_p_all:>3}sig {twr_p_all:>5.1f}% {tpnl_p_all:>+7.2f}R │ "
          f"{tn_p_htf:>3}sig {twr_p_htf:>5.1f}% {tpnl_p_htf:>+7.2f}R │ {diff_p_total:>+6.2f}")

    # Verdict
    total_filtered = sum(r["filtered"] for r in all_results)
    total_sigs = sum(r["n_all"] for r in all_results)
    print(f"\n  Signals filtered: {total_filtered}/{total_sigs + total_filtered} total generated")
    print(f"\n  {'═' * 60}")
    if diff_total > 0:
        print(f"  ✅ HTF Filter IMPROVES Full TP by {diff_total:+.2f}R")
    else:
        print(f"  ❌ HTF Filter HURTS Full TP by {diff_total:+.2f}R")
    if diff_p_total > 0:
        print(f"  ✅ HTF Filter IMPROVES Partial TP by {diff_p_total:+.2f}R")
    else:
        print(f"  ❌ HTF Filter HURTS Partial TP by {diff_p_total:+.2f}R")
    print(f"  {'═' * 60}")

    # WR comparison
    print(f"\n  Win Rate comparison:")
    print(f"    Full TP:    {twr_all:.1f}% → {twr_htf:.1f}% ({twr_htf - twr_all:+.1f}%)")
    print(f"    Partial TP: {twr_p_all:.1f}% → {twr_p_htf:.1f}% ({twr_p_htf - twr_p_all:+.1f}%)")

    # Note about data limitation
    print(f"\n  ⚠️ NOTE: Only ~3 weeks of M5 data — short-term results.")
    print(f"  Long-term HTF filter benefit may be MORE significant")
    print(f"  because counter-trend losses accumulate over months.")


if __name__ == "__main__":
    main()
