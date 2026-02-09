"""
save_data.py — Lấy dữ liệu từ TradingView và lưu file CSV

Dữ liệu lưu vào: MST Medio/data/XAUUSD_M5.csv
Timezone: UTC+7 (Vietnam)

Cách chạy:
  cd tradingview/tools
  python save_data.py                     # XAUUSD M5 5000 bars (default)
  python save_data.py EURUSD M15 3000     # Custom symbol/timeframe/bars
"""
import sys
sys.path.insert(0, '.')

from fetch_data import fetch_ohlcv
import pandas as pd
from pathlib import Path

# Data lưu trong MST Medio/data/ (cùng cấp với strategy)
DATA_DIR = Path(__file__).parent.parent / "MST Medio" / "data"


def save_tv_data(
    symbol: str = "XAUUSD",
    timeframe: str = "M5",
    bars: int = 5000,
):
    """Lấy data từ TradingView và lưu CSV."""
    df = fetch_ohlcv(symbol, timeframe, bars)
    if df.empty:
        print("❌ Không lấy được data!")
        return

    # Ensure data/ directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Save CSV
    filename = f"{symbol}_{timeframe}.csv"
    filepath = DATA_DIR / filename
    df.to_csv(filepath, float_format="%.3f")

    print(f"\n✅ Đã lưu: {filepath}")
    print(f"   Range: {df.index[0].strftime('%Y-%m-%d %H:%M')} → {df.index[-1].strftime('%Y-%m-%d %H:%M')} (UTC+7)")
    print(f"   Bars: {len(df)}")
    print(f"   Columns: {list(df.columns)}")


if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "XAUUSD"
    timeframe = sys.argv[2] if len(sys.argv) > 2 else "M5"
    bars = int(sys.argv[3]) if len(sys.argv) > 3 else 5000
    save_tv_data(symbol, timeframe, bars)
