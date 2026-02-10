import pandas as pd
import sys
sys.path.insert(0, '.')
from strategy_pa_break import find_swings

df = pd.read_csv('data/XAUUSD_M5.csv')
pivotLen = 5
swings = find_swings(df, pivotLen)
dt = df['datetime'].values

# Show swing highs and lows near Feb 4
for s in swings:
    sdt = str(dt[s.bar_index])[:22]
    if '2026-02-04' in sdt:
        print(f"{s.type:4s} @ {sdt}, price={s.price:.3f}, bar_idx={s.bar_index}")
