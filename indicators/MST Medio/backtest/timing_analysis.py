"""
timing_analysis.py — Phân tích thống kê timing cho MST Medio v2.0

Mục tiêu:
1. Chạy backtest → thu thập chi tiết từng signal
2. Phân tích win rate theo: giờ, ngày, session, bars-to-confirm, ATR
3. Đề xuất filter dựa trên data thực

Output:
- Console summary
- CSV chi tiết mỗi trade
- Recommendations
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
import numpy as np
from strategy_mst_medio import run_mst_medio, Signal
from typing import List

# ============================================================================
# CONFIG
# ============================================================================
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "analysis_output")

PAIRS = [
    ("XAUUSD", "XAUUSD_M5.csv"),
    ("EURUSD", "EURUSD_M5.csv"),
    ("USDJPY", "USDJPY_M5.csv"),
    ("BTCUSD", "BTCUSD_M5.csv"),
]

# Sessions (UTC hours)
SESSIONS = {
    "Asian":       (0, 8),    # 00:00 - 08:00 UTC
    "London":      (8, 13),   # 08:00 - 13:00 UTC
    "NY_Overlap":  (13, 16),  # 13:00 - 16:00 UTC (London+NY overlap)
    "NY_Only":     (16, 22),  # 16:00 - 22:00 UTC
    "Off_Hours":   (22, 24),  # 22:00 - 00:00 UTC (thin liquidity)
}

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# ============================================================================
# DATA LOADING
# ============================================================================
def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["datetime"])
    df.set_index("datetime", inplace=True)
    df.sort_index(inplace=True)

    for col_upper, col_lower in [
        ("Open", "open"), ("High", "high"), ("Low", "low"),
        ("Close", "close"), ("Volume", "volume")
    ]:
        if col_upper in df.columns and col_lower in df.columns:
            df[col_upper] = df[col_upper].fillna(df[col_lower])
            df.drop(columns=[col_lower], inplace=True, errors="ignore")

    df.drop(columns=["symbol"], inplace=True, errors="ignore")
    df.dropna(subset=["Open", "High", "Low", "Close"], inplace=True)
    df = df[df.index.dayofweek < 5]
    return df


# ============================================================================
# ATR CALCULATION
# ============================================================================
def calc_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate ATR for each bar."""
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)

    return tr.rolling(period).mean()


# ============================================================================
# ENRICHED SIGNAL DATA
# ============================================================================
def enrich_signals(signals: List[Signal], df: pd.DataFrame) -> pd.DataFrame:
    """Convert signals to DataFrame with timing metadata."""
    if not signals:
        return pd.DataFrame()

    atr = calc_atr(df, 14)

    records = []
    for s in signals:
        # Skip open signals
        if s.result == "OPEN":
            continue

        risk = abs(s.entry - s.sl)
        reward = abs(s.tp - s.entry) if s.tp > 0 else 0
        rr_planned = reward / risk if risk > 0 else 0

        # Timing metadata
        confirm_time = s.confirm_time
        hour = confirm_time.hour
        day_of_week = confirm_time.dayofweek  # 0=Mon, 4=Fri
        day_name = DAY_NAMES[day_of_week]

        # Session
        session = "Unknown"
        for sname, (start_h, end_h) in SESSIONS.items():
            if end_h > 24:
                if hour >= start_h or hour < (end_h - 24):
                    session = sname
                    break
            elif start_h <= hour < end_h:
                session = sname
                break

        # Bars from break to confirm
        break_time = s.break_time
        bars_to_confirm = 0
        if break_time in df.index and confirm_time in df.index:
            break_loc = df.index.get_loc(break_time)
            conf_loc = df.index.get_loc(confirm_time)
            if isinstance(break_loc, int) and isinstance(conf_loc, int):
                bars_to_confirm = conf_loc - break_loc
            elif hasattr(break_loc, 'start'):
                bars_to_confirm = conf_loc - break_loc.start if isinstance(conf_loc, int) else 0
        elif break_time != confirm_time:
            # Estimate from time difference
            td = (confirm_time - break_time).total_seconds()
            bars_to_confirm = int(td / 300)  # M5 = 300s per bar

        # ATR at confirm time
        atr_at_confirm = np.nan
        if confirm_time in atr.index:
            atr_at_confirm = atr.loc[confirm_time]
        else:
            # Find nearest ATR
            nearest_idx = atr.index.searchsorted(confirm_time)
            if nearest_idx > 0 and nearest_idx < len(atr):
                atr_at_confirm = atr.iloc[nearest_idx - 1]

        # Risk as % of price
        risk_pct = (risk / s.entry * 100) if s.entry > 0 else 0

        # Win/Loss
        is_win = s.pnl_r > 0

        records.append({
            "confirm_time": confirm_time,
            "break_time": break_time,
            "direction": s.direction,
            "entry": s.entry,
            "sl": s.sl,
            "tp": s.tp,
            "rr_planned": round(rr_planned, 2),
            "result": s.result,
            "pnl_r": round(s.pnl_r, 2),
            "is_win": is_win,
            "hour": hour,
            "day_of_week": day_of_week,
            "day_name": day_name,
            "session": session,
            "bars_to_confirm": bars_to_confirm,
            "atr_at_confirm": round(atr_at_confirm, 5) if not np.isnan(atr_at_confirm) else np.nan,
            "risk_pct": round(risk_pct, 4),
        })

    return pd.DataFrame(records)


# ============================================================================
# ANALYSIS FUNCTIONS
# ============================================================================
def analyze_by_hour(trades: pd.DataFrame) -> pd.DataFrame:
    """Win rate by hour of day."""
    if trades.empty:
        return pd.DataFrame()

    grouped = trades.groupby("hour").agg(
        total=("is_win", "count"),
        wins=("is_win", "sum"),
        pnl_r=("pnl_r", "sum"),
        avg_pnl=("pnl_r", "mean"),
    ).reset_index()
    grouped["win_rate"] = (grouped["wins"] / grouped["total"] * 100).round(1)
    grouped["pnl_r"] = grouped["pnl_r"].round(2)
    grouped["avg_pnl"] = grouped["avg_pnl"].round(2)
    return grouped.sort_values("hour")


def analyze_by_day(trades: pd.DataFrame) -> pd.DataFrame:
    """Win rate by day of week."""
    if trades.empty:
        return pd.DataFrame()

    grouped = trades.groupby(["day_of_week", "day_name"]).agg(
        total=("is_win", "count"),
        wins=("is_win", "sum"),
        pnl_r=("pnl_r", "sum"),
        avg_pnl=("pnl_r", "mean"),
    ).reset_index()
    grouped["win_rate"] = (grouped["wins"] / grouped["total"] * 100).round(1)
    grouped["pnl_r"] = grouped["pnl_r"].round(2)
    grouped["avg_pnl"] = grouped["avg_pnl"].round(2)
    return grouped.sort_values("day_of_week")


def analyze_by_session(trades: pd.DataFrame) -> pd.DataFrame:
    """Win rate by trading session."""
    if trades.empty:
        return pd.DataFrame()

    grouped = trades.groupby("session").agg(
        total=("is_win", "count"),
        wins=("is_win", "sum"),
        pnl_r=("pnl_r", "sum"),
        avg_pnl=("pnl_r", "mean"),
    ).reset_index()
    grouped["win_rate"] = (grouped["wins"] / grouped["total"] * 100).round(1)
    grouped["pnl_r"] = grouped["pnl_r"].round(2)
    grouped["avg_pnl"] = grouped["avg_pnl"].round(2)
    return grouped


def analyze_bars_to_confirm(trades: pd.DataFrame) -> pd.DataFrame:
    """Win rate bucketed by bars from break to confirm."""
    if trades.empty:
        return pd.DataFrame()

    bins = [0, 5, 10, 20, 30, 50, 100, 500, 10000]
    labels = ["1-5", "6-10", "11-20", "21-30", "31-50", "51-100", "101-500", "500+"]
    trades = trades.copy()
    trades["btc_bucket"] = pd.cut(trades["bars_to_confirm"], bins=bins, labels=labels, right=True)

    grouped = trades.groupby("btc_bucket", observed=True).agg(
        total=("is_win", "count"),
        wins=("is_win", "sum"),
        pnl_r=("pnl_r", "sum"),
        avg_pnl=("pnl_r", "mean"),
        avg_bars=("bars_to_confirm", "mean"),
    ).reset_index()
    grouped["win_rate"] = (grouped["wins"] / grouped["total"] * 100).round(1)
    grouped["pnl_r"] = grouped["pnl_r"].round(2)
    grouped["avg_pnl"] = grouped["avg_pnl"].round(2)
    grouped["avg_bars"] = grouped["avg_bars"].round(0)
    return grouped


def analyze_atr_buckets(trades: pd.DataFrame) -> pd.DataFrame:
    """Win rate by ATR percentile buckets."""
    if trades.empty or trades["atr_at_confirm"].isna().all():
        return pd.DataFrame()

    valid = trades.dropna(subset=["atr_at_confirm"]).copy()
    if len(valid) < 5:
        return pd.DataFrame()

    try:
        valid["atr_quartile"] = pd.qcut(valid["atr_at_confirm"], q=4,
                                         labels=["Low (Q1)", "Medium-Low (Q2)",
                                                  "Medium-High (Q3)", "High (Q4)"],
                                         duplicates="drop")
    except ValueError:
        # Not enough unique values for 4 quartiles
        valid["atr_quartile"] = pd.qcut(valid["atr_at_confirm"], q=2,
                                         labels=["Low", "High"],
                                         duplicates="drop")

    grouped = valid.groupby("atr_quartile", observed=True).agg(
        total=("is_win", "count"),
        wins=("is_win", "sum"),
        pnl_r=("pnl_r", "sum"),
        avg_pnl=("pnl_r", "mean"),
        atr_min=("atr_at_confirm", "min"),
        atr_max=("atr_at_confirm", "max"),
    ).reset_index()
    grouped["win_rate"] = (grouped["wins"] / grouped["total"] * 100).round(1)
    grouped["pnl_r"] = grouped["pnl_r"].round(2)
    grouped["avg_pnl"] = grouped["avg_pnl"].round(2)
    return grouped


def analyze_by_direction(trades: pd.DataFrame) -> pd.DataFrame:
    """Win rate by direction."""
    if trades.empty:
        return pd.DataFrame()

    grouped = trades.groupby("direction").agg(
        total=("is_win", "count"),
        wins=("is_win", "sum"),
        pnl_r=("pnl_r", "sum"),
        avg_pnl=("pnl_r", "mean"),
    ).reset_index()
    grouped["win_rate"] = (grouped["wins"] / grouped["total"] * 100).round(1)
    grouped["pnl_r"] = grouped["pnl_r"].round(2)
    grouped["avg_pnl"] = grouped["avg_pnl"].round(2)
    return grouped


def analyze_rr_buckets(trades: pd.DataFrame) -> pd.DataFrame:
    """Win rate by planned R:R buckets."""
    if trades.empty:
        return pd.DataFrame()

    bins = [0, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 100.0]
    labels = ["<0.5", "0.5-1.0", "1.0-1.5", "1.5-2.0", "2.0-3.0", "3.0-5.0", "5.0+"]
    t = trades.copy()
    t["rr_bucket"] = pd.cut(t["rr_planned"], bins=bins, labels=labels, right=True)

    grouped = t.groupby("rr_bucket", observed=True).agg(
        total=("is_win", "count"),
        wins=("is_win", "sum"),
        pnl_r=("pnl_r", "sum"),
        avg_pnl=("pnl_r", "mean"),
    ).reset_index()
    grouped["win_rate"] = (grouped["wins"] / grouped["total"] * 100).round(1)
    grouped["pnl_r"] = grouped["pnl_r"].round(2)
    grouped["avg_pnl"] = grouped["avg_pnl"].round(2)
    return grouped


# ============================================================================
# RECOMMENDATIONS
# ============================================================================
def generate_recommendations(trades: pd.DataFrame, pair: str) -> List[str]:
    """Generate timing filter recommendations based on data."""
    recs = []
    if trades.empty:
        return recs

    total = len(trades)
    overall_wr = trades["is_win"].mean() * 100

    # ── Session recommendations ──
    by_session = analyze_by_session(trades)
    for _, row in by_session.iterrows():
        if row["total"] >= 3:
            if row["win_rate"] < overall_wr - 15 and row["pnl_r"] < 0:
                recs.append(f"⛔ {pair}: Avoid {row['session']} session "
                           f"(WR={row['win_rate']:.0f}% vs overall {overall_wr:.0f}%, "
                           f"PnL={row['pnl_r']:+.1f}R, n={row['total']})")
            elif row["win_rate"] > overall_wr + 10 and row["pnl_r"] > 0:
                recs.append(f"✅ {pair}: {row['session']} session is strong "
                           f"(WR={row['win_rate']:.0f}%, PnL={row['pnl_r']:+.1f}R, n={row['total']})")

    # ── Day recommendations ──
    by_day = analyze_by_day(trades)
    for _, row in by_day.iterrows():
        if row["total"] >= 3:
            if row["win_rate"] < overall_wr - 15 and row["pnl_r"] < 0:
                recs.append(f"⛔ {pair}: Avoid {row['day_name']} "
                           f"(WR={row['win_rate']:.0f}%, PnL={row['pnl_r']:+.1f}R, n={row['total']})")

    # ── Bars to confirm ──
    by_btc = analyze_bars_to_confirm(trades)
    for _, row in by_btc.iterrows():
        if row["total"] >= 3:
            if row["win_rate"] < overall_wr - 15 and row["pnl_r"] < 0:
                recs.append(f"⛔ {pair}: Signals with {row['btc_bucket']} bars to confirm underperform "
                           f"(WR={row['win_rate']:.0f}%, PnL={row['pnl_r']:+.1f}R, n={row['total']})")

    # ── ATR ──
    by_atr = analyze_atr_buckets(trades)
    if not by_atr.empty:
        for _, row in by_atr.iterrows():
            if row["total"] >= 3 and row["win_rate"] < overall_wr - 15 and row["pnl_r"] < 0:
                recs.append(f"⛔ {pair}: {row['atr_quartile']} ATR environment underperforms "
                           f"(WR={row['win_rate']:.0f}%, PnL={row['pnl_r']:+.1f}R, n={row['total']})")

    # ── R:R ──
    by_rr = analyze_rr_buckets(trades)
    for _, row in by_rr.iterrows():
        if row["total"] >= 3 and row["pnl_r"] < -1:
            recs.append(f"⚠️ {pair}: R:R {row['rr_bucket']} losing money "
                       f"(PnL={row['pnl_r']:+.1f}R, WR={row['win_rate']:.0f}%, n={row['total']})")

    return recs


# ============================================================================
# MAIN
# ============================================================================
def run_analysis_for_pair(pair_name: str, data_file: str) -> pd.DataFrame:
    """Run full analysis for one pair."""
    path = os.path.join(DATA_DIR, data_file)
    if not os.path.exists(path):
        print(f"⚠️  Data file not found: {path}")
        return pd.DataFrame()

    df = load_data(path)
    print(f"\n{'#'*70}")
    print(f"# {pair_name} — {len(df)} bars ({df.index[0]} → {df.index[-1]})")
    print(f"{'#'*70}")

    # Run backtest
    signals, swings = run_mst_medio(
        df,
        pivot_len=5,
        break_mult=0.25,
        impulse_mult=1.5,
        tp_mode="confirm",
        min_rr=0.0,
        debug=False,
    )
    print(f"  Signals: {len(signals)} | Swings: {len(swings)}")

    # Enrich signals
    trades = enrich_signals(signals, df)
    if trades.empty:
        print("  No closed trades to analyze.")
        return pd.DataFrame()

    trades["pair"] = pair_name
    closed = trades[trades["result"].isin(["TP", "SL", "CLOSE_REVERSE"])]
    total = len(closed)
    wins = closed["is_win"].sum()
    wr = wins / total * 100 if total > 0 else 0
    total_r = closed["pnl_r"].sum()

    print(f"  Closed trades: {total} | WR: {wr:.1f}% | Total PnL: {total_r:+.2f} R")

    # ── Analysis by Hour ──
    print(f"\n  {'─'*50}")
    print(f"  📊 WIN RATE BY HOUR (UTC)")
    print(f"  {'─'*50}")
    by_hour = analyze_by_hour(closed)
    if not by_hour.empty:
        for _, row in by_hour.iterrows():
            bar = "█" * int(row["win_rate"] / 5)
            print(f"  {int(row['hour']):02d}:00  {bar:<20s}  WR={row['win_rate']:5.1f}%  "
                  f"PnL={row['pnl_r']:+6.1f}R  n={int(row['total']):3d}")

    # ── Analysis by Day ──
    print(f"\n  {'─'*50}")
    print(f"  📊 WIN RATE BY DAY OF WEEK")
    print(f"  {'─'*50}")
    by_day = analyze_by_day(closed)
    if not by_day.empty:
        for _, row in by_day.iterrows():
            bar = "█" * int(row["win_rate"] / 5)
            print(f"  {row['day_name']:<4s}  {bar:<20s}  WR={row['win_rate']:5.1f}%  "
                  f"PnL={row['pnl_r']:+6.1f}R  n={int(row['total']):3d}")

    # ── Analysis by Session ──
    print(f"\n  {'─'*50}")
    print(f"  📊 WIN RATE BY SESSION")
    print(f"  {'─'*50}")
    by_session = analyze_by_session(closed)
    if not by_session.empty:
        for _, row in by_session.iterrows():
            bar = "█" * int(row["win_rate"] / 5)
            print(f"  {row['session']:<14s}  {bar:<20s}  WR={row['win_rate']:5.1f}%  "
                  f"PnL={row['pnl_r']:+6.1f}R  n={int(row['total']):3d}")

    # ── Analysis by Bars to Confirm ──
    print(f"\n  {'─'*50}")
    print(f"  📊 WIN RATE BY BARS TO CONFIRM")
    print(f"  {'─'*50}")
    by_btc = analyze_bars_to_confirm(closed)
    if not by_btc.empty:
        for _, row in by_btc.iterrows():
            bar = "█" * int(row["win_rate"] / 5)
            print(f"  {str(row['btc_bucket']):<10s}  {bar:<20s}  WR={row['win_rate']:5.1f}%  "
                  f"PnL={row['pnl_r']:+6.1f}R  n={int(row['total']):3d}  avg={int(row['avg_bars'])} bars")

    # ── Analysis by ATR ──
    print(f"\n  {'─'*50}")
    print(f"  📊 WIN RATE BY ATR LEVEL")
    print(f"  {'─'*50}")
    by_atr = analyze_atr_buckets(closed)
    if not by_atr.empty:
        for _, row in by_atr.iterrows():
            bar = "█" * int(row["win_rate"] / 5)
            print(f"  {str(row['atr_quartile']):<18s}  {bar:<20s}  WR={row['win_rate']:5.1f}%  "
                  f"PnL={row['pnl_r']:+6.1f}R  n={int(row['total']):3d}")

    # ── Analysis by R:R ──
    print(f"\n  {'─'*50}")
    print(f"  📊 WIN RATE BY PLANNED R:R")
    print(f"  {'─'*50}")
    by_rr = analyze_rr_buckets(closed)
    if not by_rr.empty:
        for _, row in by_rr.iterrows():
            bar = "█" * int(row["win_rate"] / 5)
            print(f"  R:R {str(row['rr_bucket']):<8s}  {bar:<20s}  WR={row['win_rate']:5.1f}%  "
                  f"PnL={row['pnl_r']:+6.1f}R  n={int(row['total']):3d}")

    # ── Direction ──
    print(f"\n  {'─'*50}")
    print(f"  📊 WIN RATE BY DIRECTION")
    print(f"  {'─'*50}")
    by_dir = analyze_by_direction(closed)
    if not by_dir.empty:
        for _, row in by_dir.iterrows():
            bar = "█" * int(row["win_rate"] / 5)
            print(f"  {row['direction']:<5s}  {bar:<20s}  WR={row['win_rate']:5.1f}%  "
                  f"PnL={row['pnl_r']:+6.1f}R  n={int(row['total']):3d}")

    # ── Recommendations ──
    recs = generate_recommendations(closed, pair_name)
    if recs:
        print(f"\n  {'─'*50}")
        print(f"  💡 RECOMMENDATIONS")
        print(f"  {'─'*50}")
        for r in recs:
            print(f"  {r}")

    return closed


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    all_trades = []

    for pair_name, data_file in PAIRS:
        trades = run_analysis_for_pair(pair_name, data_file)
        if not trades.empty:
            all_trades.append(trades)

    # ── Combined analysis ──
    if all_trades:
        combined = pd.concat(all_trades, ignore_index=True)
        print(f"\n\n{'#'*70}")
        print(f"# COMBINED ANALYSIS — ALL PAIRS ({len(combined)} trades)")
        print(f"{'#'*70}")

        total = len(combined)
        wins = combined["is_win"].sum()
        wr = wins / total * 100 if total > 0 else 0
        total_r = combined["pnl_r"].sum()
        print(f"  Overall: {total} trades | WR={wr:.1f}% | PnL={total_r:+.2f}R")

        # Combined by session
        print(f"\n  {'─'*50}")
        print(f"  📊 COMBINED WIN RATE BY SESSION")
        print(f"  {'─'*50}")
        by_session = analyze_by_session(combined)
        if not by_session.empty:
            for _, row in by_session.iterrows():
                bar = "█" * int(row["win_rate"] / 5)
                print(f"  {row['session']:<14s}  {bar:<20s}  WR={row['win_rate']:5.1f}%  "
                      f"PnL={row['pnl_r']:+6.1f}R  n={int(row['total']):3d}")

        # Combined by bars to confirm
        print(f"\n  {'─'*50}")
        print(f"  📊 COMBINED WIN RATE BY BARS TO CONFIRM")
        print(f"  {'─'*50}")
        by_btc = analyze_bars_to_confirm(combined)
        if not by_btc.empty:
            for _, row in by_btc.iterrows():
                bar = "█" * int(row["win_rate"] / 5)
                print(f"  {str(row['btc_bucket']):<10s}  {bar:<20s}  WR={row['win_rate']:5.1f}%  "
                      f"PnL={row['pnl_r']:+6.1f}R  n={int(row['total']):3d}  avg={int(row['avg_bars'])} bars")

        # Combined recommendations
        recs = generate_recommendations(combined, "ALL_PAIRS")
        if recs:
            print(f"\n  {'─'*50}")
            print(f"  💡 COMBINED RECOMMENDATIONS")
            print(f"  {'─'*50}")
            for r in recs:
                print(f"  {r}")

        # Save to CSV
        csv_path = os.path.join(OUTPUT_DIR, "trades_detail.csv")
        combined.to_csv(csv_path, index=False)
        print(f"\n  📁 Detailed trades saved to: {csv_path}")

    print(f"\n{'='*70}")
    print(f"  Analysis complete!")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
