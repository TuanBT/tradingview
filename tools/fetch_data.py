"""
fetch_data.py — Lấy dữ liệu giá OHLCV từ nguồn free

Nguồn dữ liệu:
  1. tvdatafeed (default) — Lấy trực tiếp từ TradingView servers
     - Hỗ trợ OANDA:XAUUSD, FX, Crypto, Stock...
     - M5: ~5000 bars (~26 ngày), không giới hạn timeframe
     - Không cần login (dữ liệu có thể bị giới hạn)
  2. yfinance (fallback) — Yahoo Finance
     - M1-M30: max 7 ngày | H1-H4: max 59 ngày | D1+: không giới hạn
     - XAUUSD → GC=F (Gold Futures, giá khác OANDA!)

Timeframes: M1, M5, M15, M30, H1, H4, D1, W1, MN
"""

import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import Optional

try:
    from tvDatafeed import TvDatafeed, Interval as TvInterval
    HAS_TVDATAFEED = True
except ImportError:
    HAS_TVDATAFEED = False

try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False


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

# ── TradingView symbol mapping: tên quen thuộc → (symbol, exchange) ──
TV_SYMBOL_MAP = {
    "XAUUSD": ("XAUUSD", "OANDA"),
    "GOLD":   ("XAUUSD", "OANDA"),
    "EURUSD": ("EURUSD", "OANDA"),
    "GBPUSD": ("GBPUSD", "OANDA"),
    "USDJPY": ("USDJPY", "OANDA"),
    "AUDUSD": ("AUDUSD", "OANDA"),
    "USDCAD": ("USDCAD", "OANDA"),
    "USDCHF": ("USDCHF", "OANDA"),
    "NZDUSD": ("NZDUSD", "OANDA"),
    "EURGBP": ("EURGBP", "OANDA"),
    "XAGUSD": ("XAGUSD", "OANDA"),
    "BTCUSD": ("BTCUSD",  "COINBASE"),
    "ETHUSD": ("ETHUSD",  "COINBASE"),
    "SPX500": ("SPX500",  "FOREXCOM"),
    "NAS100": ("NAS100",  "FOREXCOM"),
}

# ── TradingView timeframe mapping ──
TV_TIMEFRAME_MAP = {
    "M1":  TvInterval.in_1_minute   if HAS_TVDATAFEED else None,
    "M5":  TvInterval.in_5_minute   if HAS_TVDATAFEED else None,
    "M15": TvInterval.in_15_minute  if HAS_TVDATAFEED else None,
    "M30": TvInterval.in_30_minute  if HAS_TVDATAFEED else None,
    "H1":  TvInterval.in_1_hour     if HAS_TVDATAFEED else None,
    "H4":  TvInterval.in_4_hour     if HAS_TVDATAFEED else None,
    "D1":  TvInterval.in_daily      if HAS_TVDATAFEED else None,
    "W1":  TvInterval.in_weekly     if HAS_TVDATAFEED else None,
    "MN":  TvInterval.in_monthly    if HAS_TVDATAFEED else None,
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


def resolve_tv_symbol(symbol: str) -> tuple:
    """Convert symbol to TradingView (symbol, exchange) tuple."""
    upper = symbol.upper().replace("/", "").replace(" ", "")
    if upper in TV_SYMBOL_MAP:
        return TV_SYMBOL_MAP[upper]
    # If contains ':', assume "EXCHANGE:SYMBOL" format
    if ":" in symbol:
        parts = symbol.split(":", 1)
        return (parts[1], parts[0])
    return (upper, "OANDA")  # default exchange


def resolve_tv_timeframe(tf: str):
    """Convert MT5-style timeframe to tvdatafeed Interval."""
    return TV_TIMEFRAME_MAP.get(tf.upper())


# ========================================================
#  tvdatafeed — TradingView data source (PRIMARY)
# ========================================================
def fetch_ohlcv_tv(
    symbol: str = "XAUUSD",
    timeframe: str = "M5",
    bars: int = 5000,
) -> pd.DataFrame:
    """
    Lấy dữ liệu OHLCV từ TradingView qua tvdatafeed.

    Args:
        symbol:    Tên cặp tiền (XAUUSD, EURUSD...) hoặc "OANDA:XAUUSD"
        timeframe: Timeframe (M1, M5, M15, H1, D1...)
        bars:      Số nến muốn lấy (max ~5000 cho nologin)

    Returns:
        DataFrame columns: Open, High, Low, Close, Volume
        Index: DatetimeIndex (timezone-aware UTC+7)
    """
    if not HAS_TVDATAFEED:
        raise ImportError("tvdatafeed chưa cài. Chạy: pip install git+https://github.com/rongardF/tvdatafeed.git")

    tv_symbol, tv_exchange = resolve_tv_symbol(symbol)
    tv_interval = resolve_tv_timeframe(timeframe)
    if tv_interval is None:
        raise ValueError(f"Timeframe '{timeframe}' không hỗ trợ cho tvdatafeed")

    print(f"📊 Fetching {tv_exchange}:{tv_symbol} | {timeframe} | {bars} bars (TradingView)...")

    tv = TvDatafeed()
    data = tv.get_hist(
        symbol=tv_symbol,
        exchange=tv_exchange,
        interval=tv_interval,
        n_bars=min(bars, 5000),
    )

    if data is None or data.empty:
        print(f"❌ Không lấy được data cho {tv_exchange}:{tv_symbol}")
        return pd.DataFrame()

    # Rename lowercase columns → uppercase
    df = data[['open', 'high', 'low', 'close', 'volume']].copy()
    df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']

    # tvdatafeed returns timezone-naive datetimes in exchange timezone
    # For OANDA forex, this is typically UTC+7 (TradingView default display)
    # We localize to UTC+7 for consistency
    TZ_VN = timezone(timedelta(hours=7))
    df.index = df.index.tz_localize(TZ_VN)

    print(f"✅ Đã lấy {len(df)} nến | "
          f"Từ {df.index[0].strftime('%Y-%m-%d %H:%M')} → {df.index[-1].strftime('%Y-%m-%d %H:%M')} (UTC+7)")

    return df


# ========================================================
#  yfinance — Yahoo Finance data source (FALLBACK)
# ========================================================


def fetch_ohlcv(
    symbol: str = "XAUUSD",
    timeframe: str = "M15",
    bars: int = 500,
    end_date: Optional[str] = None,
    start_date: Optional[str] = None,
    source: str = "auto",
) -> pd.DataFrame:
    """
    Lấy dữ liệu OHLCV.

    Args:
        symbol:     Tên cặp tiền (XAUUSD, EURUSD, BTCUSD, AAPL...)
        timeframe:  Timeframe (M1, M5, M15, H1, D1, W1...)
        bars:       Số nến muốn lấy
        end_date:   Ngày kết thúc (YYYY-MM-DD), None = hiện tại  [chỉ yfinance]
        start_date: Ngày bắt đầu (YYYY-MM-DD), None = auto       [chỉ yfinance]
        source:     "auto" (ưu tiên tvdatafeed), "tv", hoặc "yfinance"

    Returns:
        DataFrame với columns: Open, High, Low, Close, Volume
        Index: DatetimeIndex (timezone-aware)
    """
    # Route to tvdatafeed if available (preferred)
    use_tv = (
        source in ("auto", "tv")
        and HAS_TVDATAFEED
        and start_date is None
        and end_date is None
    )
    if use_tv:
        try:
            return fetch_ohlcv_tv(symbol, timeframe, bars)
        except Exception as e:
            if source == "tv":
                raise
            print(f"⚠️ tvdatafeed failed: {e} — Falling back to yfinance...")

    # Fallback to yfinance
    if not HAS_YFINANCE:
        raise ImportError("Cần cài ít nhất 1 nguồn: tvdatafeed hoặc yfinance")

    return _fetch_ohlcv_yfinance(symbol, timeframe, bars, end_date, start_date)


def _fetch_ohlcv_yfinance(
    symbol: str = "XAUUSD",
    timeframe: str = "M15",
    bars: int = 500,
    end_date: Optional[str] = None,
    start_date: Optional[str] = None,
) -> pd.DataFrame:
    """Fetch OHLCV from yfinance (internal)."""
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
    if start_date:
        start = pd.Timestamp(start_date)
    else:
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
