"""Print detailed XAUUSD M5 signal list for visual verification."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import pandas as pd
from strategy_mst_medio import run_mst_medio

# Load XAUUSD M5
df = pd.read_csv(os.path.join(os.path.dirname(__file__), "..", "data", "BTCUSD_M5.csv"),
                 parse_dates=["datetime"])
df.set_index("datetime", inplace=True)
df.sort_index(inplace=True)
for cu, cl in [("Open","open"),("High","high"),("Low","low"),("Close","close"),("Volume","volume")]:
    if cu in df.columns and cl in df.columns:
        df[cu] = df[cu].fillna(df[cl])
        df.drop(columns=[cl], inplace=True, errors="ignore")
df.drop(columns=["symbol"], inplace=True, errors="ignore")
df.dropna(subset=["Open","High","Low","Close"], inplace=True)
df = df[df.index.dayofweek < 5]

signals, swings = run_mst_medio(df, pivot_len=5, break_mult=0.25, impulse_mult=1.5,
                                 min_rr=0, sl_buffer_pct=0, tp_mode="confirm", debug=False)

print(f"Total: {len(signals)} signals\n")
header = f"{'#':>3} {'Dir':>5} {'Break Time':>22} {'Confirm Time':>22} {'Entry':>10} {'SL':>10} {'TP':>10} {'Result':>8} {'PnL(R)':>8}"
print(header)
print("-" * len(header))
for i, s in enumerate(signals, 1):
    print(f"{i:>3} {s.direction:>5} {str(s.break_time):>22} {str(s.confirm_time):>22} "
          f"{s.entry:>10.2f} {s.sl:>10.2f} {s.tp:>10.2f} {s.result:>8} {s.pnl_r:>+8.2f}")
