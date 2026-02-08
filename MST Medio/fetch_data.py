"""
fetch_data.py — Lấy dữ liệu giá OHLCV từ nguồn free (yfinance)

Symbols phổ biến trên yfinance:
  Forex:  EURUSD=X, GBPUSD=X, USDJPY=X
  Gold:   GC=F (futures), XAUUSD không có trực tiếp → dùng GC=F
  Silver: SI=F
  Oil:    CL=F
  Crypto: BTC-USD, ETH-USD
  Stock:  AAPL, MSFT, TSLA

Timeframes yfinance hỗ trợ:
  1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h  (max 7 ngày history cho ≤1h)
  1d, 5d, 1wk, 1mo, 3mo               (không giới hạn)
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional


# ── Symbol mapping: tên quen thuộc → yfinance ticker ──
SYMBOL_MAP = {
    # Forex
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "AUDUSD": "AUDUSD=X",
    "USDCAD": "USDCAD=X",
    "USDCHF": "USDCHF=X",
    "NZDUSD": "NZDUSD=X",
    "EURGBP": "EURGBP=X",
    # Commodities
    "XAUUSD": "GC=F",      # Gold futures
    "GOLD":   "GC=F",
    "SILVER": "SI=F",
    "OIL":    "CL=F",
    "XAGUSD": "SI=F",
    # Crypto
    "BTCUSD": "BTC-USD",
    "ETHUSD": "ETH-USD",
    "BTCUSDT": "BTC-USD",
    # Indices
    "SPX500": "^GSPC",
    "NAS100": "^IXIC",
    "DJI":    "^DJI",
    "VN30":   "^VN30",
}

# ── Timeframe mapping: MT5-style → yfinance interval ──
TIMEFRAME_MAP = {
    "M1":  "1m",
    "M5":  "5m",
    "M15": "15m",
    "M30": "30m",
    "H1":  "1h",
    "H4":  "1h",   # yfinance không có H4, sẽ resample
    "D1":  "1d",
    "W1":  "1wk",
    "MN":  "1mo",
    # Direct yfinance values also accepted
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "1d": "1d", "1wk": "1wk", "1mo": "1mo",
}


def resolve_symbol(symbol: str) -> str:
    """Convert MT5-style symbol to yfinance ticker."""
    upper = symbol.upper().replace("/", "").replace(" ", "")
    return SYMBOL_MAP.get(upper, symbol)


def resolve_timeframe(tf: str) -> str:
    """Convert MT5-style timeframe to yfinance interval."""
    return TIMEFRAME_MAP.get(tf.upper(), tf)


def fetch_ohlcv(
    symbol: str = "XAUUSD",
    timeframe: str = "M15",
    bars: int = 500,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """
    Lấy dữ liệu OHLCV.

    Args:
        symbol:    Tên cặp tiền (XAUUSD, EURUSD, BTCUSD, AAPL...)
        timeframe: Timeframe (M1, M5, M15, H1, D1, W1...)
        bars:      Số nến muốn lấy
        end_date:  Ngày kết thúc (YYYY-MM-DD), None = hiện tại

    Returns:
        DataFrame với columns: Open, High, Low, Close, Volume
        Index: DatetimeIndex (UTC)
    """
    ticker = resolve_symbol(symbol)
    interval = resolve_timeframe(timeframe)
    need_resample_h4 = timeframe.upper() == "H4"

    # Tính period cần download
    if end_date:
        end = pd.Timestamp(end_date)
    else:
        end = pd.Timestamp.now()

    # Estimate start date based on timeframe
    tf_minutes = {
        "1m": 1, "5m": 5, "15m": 15, "30m": 30,
        "1h": 60, "1d": 1440, "1wk": 10080, "1mo": 43200,
    }
    minutes = tf_minutes.get(interval, 1440)
    if need_resample_h4:
        minutes = 240
        bars_to_fetch = bars * 4 + 100  # fetch 4x H1 bars for H4 resample
    else:
        bars_to_fetch = bars

    # Add extra buffer for weekends/holidays
    total_minutes = minutes * bars_to_fetch * 1.8
    start = end - timedelta(minutes=total_minutes)

    # yfinance giới hạn intraday data
    if interval in ["1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h"]:
        max_days = 59 if interval in ["1h", "60m", "90m"] else 7
        if (end - start).days > max_days:
            start = end - timedelta(days=max_days)
            print(f"⚠️ yfinance giới hạn {interval} data: max {max_days} ngày."
                  f" Lấy từ {start.date()}")

    print(f"📊 Fetching {symbol} ({ticker}) | {timeframe} | {bars} bars...")

    data = yf.download(
        ticker,
        start=start.strftime("%Y-%m-%d"),
        end=(end + timedelta(days=1)).strftime("%Y-%m-%d"),
        interval=interval,
        auto_adjust=True,
        progress=False,
    )

    if data.empty:
        print(f"❌ Không lấy được data cho {symbol} ({ticker})")
        return pd.DataFrame()

    # Flatten MultiIndex columns if present
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    # Resample H4 from H1
    if need_resample_h4:
        data = data.resample("4h").agg({
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }).dropna()

    # Giữ chỉ số nến cần
    data = data.tail(bars)

    # Chuẩn hóa column names
    data = data.rename(columns={
        "Open": "Open", "High": "High", "Low": "Low",
        "Close": "Close", "Volume": "Volume",
    })

    # Ensure standard columns exist
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col not in data.columns:
            data[col] = 0.0

    print(f"✅ Đã lấy {len(data)} nến | "
          f"Từ {data.index[0]} → {data.index[-1]}")

    return data[["Open", "High", "Low", "Close", "Volume"]]


def show_available_symbols():
    """Hiển thị danh sách symbols có sẵn."""
    print("\n📋 Symbols có sẵn:")
    print("=" * 50)
    categories = {
        "Forex": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF"],
        "Commodities": ["XAUUSD (Gold)", "XAGUSD (Silver)", "OIL"],
        "Crypto": ["BTCUSD", "ETHUSD"],
        "Indices": ["SPX500", "NAS100", "DJI"],
    }
    for cat, symbols in categories.items():
        print(f"\n  {cat}:")
        for s in symbols:
            print(f"    • {s}")

    print("\n📋 Timeframes:")
    print("  M1, M5, M15, M30, H1, H4, D1, W1, MN")
    print("  ⚠️ M1-M30: max 7 ngày | H1-H4: max 59 ngày | D1+: không giới hạn")


# ── Quick test ──
if __name__ == "__main__":
    show_available_symbols()
    print("\n" + "=" * 50)

    # Test lấy data Gold D1
    df = fetch_ohlcv("XAUUSD", "D1", bars=100)
    if not df.empty:
        print(f"\n📊 XAUUSD D1 — Last 5 bars:")
        print(df.tail())
        print(f"\nHigh: {df['High'].max():.2f} | Low: {df['Low'].min():.2f}")
