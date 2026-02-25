"""
backtest_multi_pair.py — MST Medio v2.0 backtest on multiple pairs (M5)
Pairs: BTCUSDT, XAUUSD, USOILUSD, EURUSD, USDJPY
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from tvDatafeed import TvDatafeed, Interval
from strategy_mst_medio import run_mst_medio, print_summary

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

# ── Pair config: (symbol, exchange, filename) ──
PAIRS = [
    ("XAUUSD", "OANDA",    "XAUUSD_M5.csv"),
    ("BTCUSD", "BINANCE",  "BTCUSD_M5.csv"),
    ("USOILUSDT.P", "BTCC", "USOIL_M5.csv"),
    ("EURUSD", "OANDA",     "EURUSD_M5.csv"),
    ("USDJPY", "OANDA",     "USDJPY_M5.csv"),
]

N_BARS = 5000  # ~17 days of M5 data


def fetch_m5_data(symbol: str, exchange: str) -> pd.DataFrame:
    """Download M5 data from TradingView via tvdatafeed."""
    tv = TvDatafeed()
    df = tv.get_hist(symbol=symbol, exchange=exchange, interval=Interval.in_5_minute, n_bars=N_BARS)
    if df is None or len(df) == 0:
        raise ValueError(f"No data returned for {symbol} ({exchange})")
    # Standardize columns
    df.index.name = "datetime"
    df.columns = [c.capitalize() if c != "symbol" else c for c in df.columns]
    # Rename 'Open' etc. (already capitalized)
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col.lower() in df.columns:
            df.rename(columns={col.lower(): col}, inplace=True)
    df.drop(columns=["symbol"], inplace=True, errors="ignore")
    df.dropna(subset=["Open", "High", "Low", "Close"], inplace=True)
    return df


def load_or_fetch(symbol: str, exchange: str, filename: str) -> pd.DataFrame:
    """Load from CSV if fresh (< 1 day old), otherwise fetch and save."""
    filepath = os.path.join(DATA_DIR, filename)

    # Always fetch fresh data for backtest comparison
    print(f"  Fetching {symbol} M5 from {exchange}...", end=" ", flush=True)
    df = fetch_m5_data(symbol, exchange)
    os.makedirs(DATA_DIR, exist_ok=True)
    df.to_csv(filepath)
    print(f"✅ {len(df)} bars ({df.index[0]} → {df.index[-1]})")
    return df


def run_pair_backtest(symbol: str, df: pd.DataFrame) -> dict:
    """Run backtest on a single pair, return summary dict."""
    # Remove weekends (forex/commodities)
    df = df[df.index.dayofweek < 5].copy() if symbol not in ("BTCUSDT",) else df.copy()

    signals, swings = run_mst_medio(
        df,
        pivot_len=5,
        break_mult=0.25,
        impulse_mult=1.5,
        min_rr=0,
        tp_mode="confirm",
        debug=False,
    )

    total = len(signals)
    if total == 0:
        return {
            "symbol": symbol,
            "bars": len(df),
            "days": (df.index[-1] - df.index[0]).days if len(df) > 1 else 0,
            "signals": 0,
            "wins": 0,
            "wr": 0,
            "pnl_r": 0,
            "buy_n": 0, "buy_wr": 0, "buy_pnl": 0,
            "sell_n": 0, "sell_wr": 0, "sell_pnl": 0,
        }

    wins = sum(1 for s in signals if s.result == "TP")
    wr = wins / total * 100
    pnl = sum(s.pnl_r for s in signals)

    buys = [s for s in signals if s.direction == "BUY"]
    sells = [s for s in signals if s.direction == "SELL"]
    buy_wins = sum(1 for s in buys if s.result == "TP")
    sell_wins = sum(1 for s in sells if s.result == "TP")

    return {
        "symbol": symbol,
        "bars": len(df),
        "days": (df.index[-1] - df.index[0]).days if len(df) > 1 else 0,
        "signals": total,
        "wins": wins,
        "wr": wr,
        "pnl_r": pnl,
        "buy_n": len(buys),
        "buy_wr": (buy_wins / len(buys) * 100) if buys else 0,
        "buy_pnl": sum(s.pnl_r for s in buys),
        "sell_n": len(sells),
        "sell_wr": (sell_wins / len(sells) * 100) if sells else 0,
        "sell_pnl": sum(s.pnl_r for s in sells),
    }


def main():
    print("=" * 75)
    print("MST Medio v2.0 — Multi-Pair M5 Backtest")
    print("=" * 75)

    results = []

    for symbol, exchange, filename in PAIRS:
        print(f"\n{'─' * 60}")
        print(f"▶ {symbol}")
        print(f"{'─' * 60}")

        try:
            df = load_or_fetch(symbol, exchange, filename)
            res = run_pair_backtest(symbol, df)
            results.append(res)

            # Print individual result
            print(f"  {res['bars']} bars | {res['days']} days")
            print(f"  Signals: {res['signals']} | WR: {res['wr']:.1f}% | PnL: {res['pnl_r']:+.2f}R")
            print(f"  BUY:  {res['buy_n']} trades | WR: {res['buy_wr']:.1f}% | PnL: {res['buy_pnl']:+.2f}R")
            print(f"  SELL: {res['sell_n']} trades | WR: {res['sell_wr']:.1f}% | PnL: {res['sell_pnl']:+.2f}R")

        except Exception as e:
            print(f"  ❌ Error: {e}")
            results.append({
                "symbol": symbol, "bars": 0, "days": 0,
                "signals": 0, "wins": 0, "wr": 0, "pnl_r": 0,
                "buy_n": 0, "buy_wr": 0, "buy_pnl": 0,
                "sell_n": 0, "sell_wr": 0, "sell_pnl": 0,
            })

    # ── Summary Table ──
    print(f"\n\n{'=' * 75}")
    print("SUMMARY — MST Medio v2.0 M5 Backtest (TP = Confirm Peak)")
    print(f"{'=' * 75}")
    print(f"{'Symbol':<12} {'Days':>5} {'Bars':>6} {'Signals':>8} {'WR%':>7} {'PnL(R)':>8} {'BUY':>6} {'SELL':>6}")
    print("-" * 75)

    total_signals = 0
    total_wins = 0
    total_pnl = 0

    for r in results:
        print(f"{r['symbol']:<12} {r['days']:>5} {r['bars']:>6} {r['signals']:>8} "
              f"{r['wr']:>6.1f}% {r['pnl_r']:>+7.2f} "
              f"{r['buy_n']:>3}/{r['buy_wr']:.0f}% "
              f"{r['sell_n']:>3}/{r['sell_wr']:.0f}%")
        total_signals += r["signals"]
        total_wins += r["wins"]
        total_pnl += r["pnl_r"]

    print("-" * 75)
    total_wr = total_wins / total_signals * 100 if total_signals > 0 else 0
    print(f"{'TOTAL':<12} {'':>5} {'':>6} {total_signals:>8} "
          f"{total_wr:>6.1f}% {total_pnl:>+7.2f}")
    print()


if __name__ == "__main__":
    main()
