"""
backtest_v2.py — Run MST Medio v2.0 backtest on M5 data
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from strategy_mst_medio import run_mst_medio, signals_to_dataframe, print_summary

DATA_M5 = os.path.join(os.path.dirname(__file__), "..", "data", "XAUUSD_M5.csv")
DATA_M15 = os.path.join(os.path.dirname(__file__), "..", "data", "XAUUSD_M15.csv")

def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["datetime"])
    df.set_index("datetime", inplace=True)
    df.sort_index(inplace=True)
    
    # Merge uppercase and lowercase columns (from CSV merge artifact)
    # Old data uses Open/High/Low/Close, new data uses open/high/low/close
    for col_upper, col_lower in [("Open", "open"), ("High", "high"), ("Low", "low"), ("Close", "close"), ("Volume", "volume")]:
        if col_upper in df.columns and col_lower in df.columns:
            df[col_upper] = df[col_upper].fillna(df[col_lower])
            df.drop(columns=[col_lower], inplace=True, errors="ignore")
    
    # Drop symbol column
    df.drop(columns=["symbol"], inplace=True, errors="ignore")
    
    # Drop rows that are still NaN
    df.dropna(subset=["Open", "High", "Low", "Close"], inplace=True)
    
    # Remove weekends
    df = df[df.index.dayofweek < 5]
    return df

def main():
    for label, path in [("M5", DATA_M5), ("M15", DATA_M15)]:
        if not os.path.exists(path):
            print(f"⚠️  {label} data not found: {path}")
            continue
        print(f"\n{'#'*70}")
        print(f"# {label} DATA")
        print(f"{'#'*70}")
        df = load_data(path)
        print(f"Loaded {len(df)} bars: {df.index[0]} → {df.index[-1]}")

        # ── Main backtest: TP = Confirm candle high/low ──
        print(f"\n▶ {label}: MST Medio v2.0 — TP = Confirm Peak")
        signals, swings = run_mst_medio(
            df,
            pivot_len=5,
            break_mult=0.25,
            impulse_mult=1.5,
            tp_mode="confirm",
            min_rr=0.0,
            debug=False,
        )
        print_summary(signals, title=f"{label}: MST Medio v2.0 — TP = Confirm Peak")

        # ── With min R:R filter ──
        print(f"\n▶ {label}: TP = Confirm Peak, Min R:R ≥ 1.0")
        signals_rr, _ = run_mst_medio(
            df,
            pivot_len=5,
            break_mult=0.25,
            impulse_mult=1.5,
            tp_mode="confirm",
            min_rr=1.0,
            debug=False,
        )
        print_summary(signals_rr, title=f"{label}: TP = Confirm Peak, Min R:R ≥ 1.0")

        # ── Fixed R:R comparison ──
        for rr in [1.5, 2.0, 3.0]:
            signals_fix, _ = run_mst_medio(
                df,
                pivot_len=5,
                break_mult=0.25,
                impulse_mult=1.5,
                tp_mode="fixed_rr",
                fixed_rr=rr,
                min_rr=0.0,
                debug=False,
            )
            print_summary(signals_fix, title=f"{label}: Fixed R:R = {rr}")

if __name__ == "__main__":
    main()
