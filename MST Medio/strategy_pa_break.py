"""
strategy_pa_break.py — Python version of PA Break strategy

Logic khớp PA Break.pine v0.7.0 (Wave Confirmation):
1. Tìm Swing High / Swing Low (pivot)
2. Detect HH (Higher High) / LL (Lower Low) + Impulse Body Filter
3. Sau break: track mini-waves (chuỗi nến cùng chiều)
4. Confirm: Wave 2 peak > Wave 1 peak AND vượt break point → chờ retest
5. Entry = break point (sh1 cho BUY, sl1 cho SELL)
6. SL = swing đối diện trước break
"""

__version__ = "v0.7.0 — Wave Confirmation"

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Signal:
    """Một tín hiệu trade."""
    time: pd.Timestamp
    direction: str          # "BUY" or "SELL"
    entry: float
    sl: float
    tp: float
    break_point: float      # HH or LL that triggered the break
    break_time: pd.Timestamp
    confirm_time: pd.Timestamp
    wave_confirm_time: pd.Timestamp = None  # bar when wave confirmed
    result: str = ""        # "TP", "SL", "CLOSE_REVERSE", "OPEN"
    pnl_r: float = 0.0     # P&L in R units


@dataclass
class SwingPoint:
    """Một swing point."""
    time: pd.Timestamp
    price: float
    type: str               # "HIGH" or "LOW"
    bar_index: int


def find_swings(df: pd.DataFrame, pivot_len: int = 5) -> List[SwingPoint]:
    """
    Tìm tất cả Swing High và Swing Low trong data.

    Pivot High: high[i] là cao nhất trong [i-pivot_len, i+pivot_len]
    Pivot Low:  low[i] là thấp nhất trong [i-pivot_len, i+pivot_len]

    Returns: List[SwingPoint] sorted by time
    """
    swings = []
    highs = df["High"].values
    lows = df["Low"].values
    times = df.index

    for i in range(pivot_len, len(df) - pivot_len):
        # Check Pivot High
        is_ph = True
        for j in range(i - pivot_len, i + pivot_len + 1):
            if j == i:
                continue
            if highs[j] >= highs[i]:
                is_ph = False
                break
        if is_ph:
            swings.append(SwingPoint(
                time=times[i], price=highs[i],
                type="HIGH", bar_index=i
            ))

        # Check Pivot Low
        is_pl = True
        for j in range(i - pivot_len, i + pivot_len + 1):
            if j == i:
                continue
            if lows[j] <= lows[i]:
                is_pl = False
                break
        if is_pl:
            swings.append(SwingPoint(
                time=times[i], price=lows[i],
                type="LOW", bar_index=i
            ))

    swings.sort(key=lambda s: s.time)
    return swings


def run_pa_break(
    df: pd.DataFrame,
    pivot_len: int = 5,
    rr_ratio: float = 2.0,
    sl_buffer_pct: float = 0.002,   # 0.2% SL buffer (thay ATR cho đơn giản)
    break_mult: float = 0.0,        # Break strength filter (0=OFF)
    impulse_mult: float = 1.5,      # Impulse body filter (0=OFF)
) -> tuple[List[Signal], List[SwingPoint]]:
    """
    Chạy PA Break strategy trên historical data.
    v0.7.0 — Wave Confirmation: Break + Mini-Wave HH/LL Confirm.

    Sau HH/LL break (impulse candle), track mini-waves:
    - Wave = chuỗi nến cùng chiều (xanh liên tiếp hoặc đỏ liên tiếp)
    - Khi đổi màu = kết thúc wave, ghi nhận peak/trough
    - Wave 2 peak > Wave 1 peak (BUY) → CONFIRM → vào lệnh
    - Entry = break point (sh1/sl1), SL = swing đối diện

    Args:
        df:            DataFrame OHLCV
        pivot_len:     Pivot lookback
        rr_ratio:      Risk:Reward ratio cho TP (0=không có TP)
        sl_buffer_pct: SL buffer percentage (thay cho ATR buffer)
        break_mult:    Break strength filter (0=OFF)
        impulse_mult:  Nến break phải có body >= impulse_mult × avg body (0=OFF)

    Returns:
        (signals, swings)
    """
    swings = find_swings(df, pivot_len)
    if len(swings) < 4:
        return [], swings

    signals: List[Signal] = []
    highs = df["High"].values
    lows = df["Low"].values
    closes = df["Close"].values
    opens = df["Open"].values
    times = df.index

    # State tracking
    sh1 = sh0 = None
    sl1 = sl0 = None
    sh1_time = sh0_time = None
    sl1_time = sl0_time = None
    sl_before_sh = None
    sh_before_sl = None

    # Recent max/min tracking for true HH/LL detection
    sh_recent_max = None       # Highest SH since last valid break
    sl_recent_min = None       # Lowest SL since last valid break

    # Group tracking (legacy, kept for compatibility)
    sh_group_max = None
    sh_group_max_time = None
    sl_group_min = None
    sl_group_min_time = None

    # ── Wave Confirmation State ──
    # pending_dir: 0=idle,
    #   1=pendingBuyWave (tracking waves after HH break),
    #   2=pendingBuyRetest (wave confirmed, waiting for retest at break point),
    #  -1=pendingSellWave (tracking waves after LL break),
    #  -2=pendingSellRetest (wave confirmed, waiting for retest at break point)
    pending_dir = 0
    pend_break_point = None    # sh1 (BUY) or sl1 (SELL) = entry level
    pend_sl = None             # SL level
    pend_sl_time = None
    pend_break_time = None

    # Mini-wave tracking
    wave_count = 0             # How many complete up-waves seen (BUY) / down-waves (SELL)
    wave1_peak = None          # Peak of wave 1 (BUY) or trough of wave 1 (SELL)
    wave2_peak = None          # Peak of wave 2 (BUY) or trough of wave 2 (SELL)
    in_up_wave = False         # Currently in an up-wave?
    in_down_wave = False       # Currently in a down-wave?
    current_wave_peak = None   # Running max HIGH of current up-wave (BUY)
    current_wave_trough = None # Running min LOW of current down-wave (SELL)
    wave_conf_time = None      # Bar time when wave confirmed

    # Active signal tracking
    active_signal: Optional[Signal] = None

    # Process swings and bars
    swing_idx = 0

    for bar_i in range(pivot_len, len(df)):
        bar_time = times[bar_i]
        bar_high = highs[bar_i]
        bar_low = lows[bar_i]
        bar_close = closes[bar_i]
        bar_open = opens[bar_i]
        is_bullish = bar_close >= bar_open

        # Check if any swing is confirmed at this bar
        confirmed_bar = bar_i - pivot_len
        if confirmed_bar < 0:
            continue

        is_sw_h = False
        is_sw_l = False
        check_high = highs[confirmed_bar]
        check_low = lows[confirmed_bar]
        check_time = times[confirmed_bar]

        while swing_idx < len(swings) and swings[swing_idx].bar_index < confirmed_bar:
            swing_idx += 1

        if swing_idx < len(swings) and swings[swing_idx].bar_index == confirmed_bar:
            sw = swings[swing_idx]
            if sw.type == "HIGH":
                is_sw_h = True
            if sw.type == "LOW":
                is_sw_l = True
            if swing_idx + 1 < len(swings) and swings[swing_idx + 1].bar_index == confirmed_bar:
                sw2 = swings[swing_idx + 1]
                if sw2.type == "HIGH":
                    is_sw_h = True
                if sw2.type == "LOW":
                    is_sw_l = True

        # ── Update Swing Low ──
        if is_sw_l:
            if sl1 is not None:
                if sl_group_min is None or sl1 < sl_group_min:
                    sl_group_min = sl1
                    sl_group_min_time = sl1_time
            sl0, sl0_time = sl1, sl1_time
            sl1, sl1_time = check_low, check_time
            # Track lowest SL for true LL detection
            if sl_recent_min is None or check_low < sl_recent_min:
                sl_recent_min = check_low

        # ── Update Swing High ──
        if is_sw_h:
            if sh1 is not None:
                if sh_group_max is None or sh1 > sh_group_max:
                    sh_group_max = sh1
                    sh_group_max_time = sh1_time
            sl_before_sh = sl1
            sh0, sh0_time = sh1, sh1_time
            sh1, sh1_time = check_high, check_time
            # Track highest SH for true HH detection
            if sh_recent_max is None or check_high > sh_recent_max:
                sh_recent_max = check_high

        if is_sw_l:
            sh_before_sl = sh1

        # ── HH / LL Detection (true HH: must exceed ALL recent SH) ──
        is_new_hh = is_sw_h and sh0 is not None and sh1 > sh0 and (sh_recent_max is None or sh1 >= sh_recent_max)
        is_new_ll = is_sw_l and sl0 is not None and sl1 < sl0 and (sl_recent_min is None or sl1 <= sl_recent_min)

        # ── Impulse Body Filter ──
        if impulse_mult > 0:
            bodies = np.abs(closes[:bar_i+1] - opens[:bar_i+1])
            avg_body = np.mean(bodies[max(0, bar_i-19):bar_i+1]) if bar_i >= 1 else 1.0

            if is_new_hh and sh0 is not None:
                sh0_bi = next((s.bar_index for s in swings if s.type == "HIGH" and s.price == sh0), confirmed_bar)
                found_impulse = False
                for j in range(sh0_bi, confirmed_bar + 1):
                    if j < len(closes) and closes[j] > sh0:
                        body_j = abs(closes[j] - opens[j])
                        found_impulse = (body_j >= impulse_mult * avg_body)
                        break
                if not found_impulse:
                    is_new_hh = False

            if is_new_ll and sl0 is not None:
                sl0_bi = next((s.bar_index for s in swings if s.type == "LOW" and s.price == sl0), confirmed_bar)
                found_impulse = False
                for j in range(sl0_bi, confirmed_bar + 1):
                    if j < len(closes) and closes[j] < sl0:
                        body_j = abs(closes[j] - opens[j])
                        found_impulse = (body_j >= impulse_mult * avg_body)
                        break
                if not found_impulse:
                    is_new_ll = False

        # ── Break Strength Filter ──
        raw_break_up = False
        raw_break_down = False

        if is_new_hh and sl_before_sh is not None:
            if break_mult <= 0:
                raw_break_up = True
            else:
                swing_range = sh0 - sl_before_sh
                break_dist = sh1 - sh0
                if swing_range > 0 and break_dist >= swing_range * break_mult:
                    raw_break_up = True

        if is_new_ll and sh_before_sl is not None:
            if break_mult <= 0:
                raw_break_down = True
            else:
                swing_range = sh_before_sl - sl0
                break_dist = sl0 - sl1
                if swing_range > 0 and break_dist >= swing_range * break_mult:
                    raw_break_down = True

        # ── Wave Confirmation Logic ──
        confirmed_buy = False
        confirmed_sell = False

        # ── Phase 2: Retest at break point (limit order fills) ──
        if pending_dir == 2 and pend_break_point is not None:
            # SL invalidation
            if pend_sl is not None and bar_low <= pend_sl:
                pending_dir = 0
            elif bar_low <= pend_break_point:
                confirmed_buy = True
                pending_dir = 0

        if pending_dir == -2 and pend_break_point is not None:
            # SL invalidation
            if pend_sl is not None and bar_high >= pend_sl:
                pending_dir = 0
            elif bar_high >= pend_break_point:
                confirmed_sell = True
                pending_dir = 0

        # ── Phase 1: Wave tracking after break ──
        if pending_dir == 1:
            # ── BUY: tracking mini-waves after HH break ──
            # SL invalidation
            if pend_sl is not None and bar_low <= pend_sl:
                pending_dir = 0
            else:
                # Track up-waves: consecutive bullish candles
                if is_bullish:
                    if not in_up_wave:
                        # Starting new up-wave
                        in_up_wave = True
                        in_down_wave = False
                        current_wave_peak = bar_high
                    else:
                        # Continue up-wave
                        if bar_high > current_wave_peak:
                            current_wave_peak = bar_high
                else:
                    # Bearish candle
                    if in_up_wave:
                        # Include this bar's HIGH in the wave peak (râu có thể cao hơn)
                        if bar_high > current_wave_peak:
                            current_wave_peak = bar_high
                        # Up-wave just ended
                        wave_count += 1
                        if wave_count == 1:
                            wave1_peak = current_wave_peak
                        elif wave_count >= 2:
                            wave2_peak = current_wave_peak
                            # Check confirm: wave2 > wave1 AND wave2 > break point
                            if wave2_peak > wave1_peak and wave2_peak > pend_break_point:
                                # Wave confirmed! → Move to retest phase
                                pending_dir = 2
                                wave_conf_time = bar_time
                        in_up_wave = False
                        in_down_wave = True
                        current_wave_peak = None
                    else:
                        in_down_wave = True

        elif pending_dir == -1:
            # ── SELL: tracking mini-waves after LL break ──
            # SL invalidation
            if pend_sl is not None and bar_high >= pend_sl:
                pending_dir = 0
            else:
                # Track down-waves: consecutive bearish candles
                if not is_bullish:
                    if not in_down_wave:
                        in_down_wave = True
                        in_up_wave = False
                        current_wave_trough = bar_low
                    else:
                        if bar_low < current_wave_trough:
                            current_wave_trough = bar_low
                else:
                    # Bullish candle
                    if in_down_wave:
                        # Include this bar's LOW in the wave trough
                        if bar_low < current_wave_trough:
                            current_wave_trough = bar_low
                        # Down-wave just ended
                        wave_count += 1
                        if wave_count == 1:
                            wave1_peak = current_wave_trough  # "peak" = trough for SELL
                        elif wave_count >= 2:
                            wave2_peak = current_wave_trough
                            # Check confirm: wave2 < wave1 AND wave2 < break point
                            if wave2_peak < wave1_peak and wave2_peak < pend_break_point:
                                # Wave confirmed! → Move to retest phase
                                pending_dir = -2
                                wave_conf_time = bar_time
                        in_down_wave = False
                        in_up_wave = True
                        current_wave_trough = None
                    else:
                        in_up_wave = True

        # ── New raw break → start wave tracking (overrides old wave tracking) ──
        # BUT: don't override if in retest phase (already confirmed)
        if raw_break_up and pending_dir != 2:
            pending_dir = 1
            pend_break_point = sh1
            pend_sl = sl_before_sh
            pend_sl_time = sl1_time if sl_before_sh == sl1 else None
            pend_break_time = sh1_time
            # Reset recent tracking (new cycle)
            sh_recent_max = sh1
            sl_recent_min = None
            # Reset wave state
            wave_count = 0
            wave1_peak = None
            wave2_peak = None
            in_up_wave = False
            in_down_wave = False
            current_wave_peak = None
            current_wave_trough = None

            # The break candle itself starts wave 1
            # Find the impulse candle (first close > sh0)
            # Waves start from the bar after sh1 is confirmed (= current bar)
            # Actually, the impulse candle already happened. We start tracking
            # waves from current bar onwards.

        if raw_break_down and pending_dir != -2:
            pending_dir = -1
            pend_break_point = sl1
            pend_sl = sh_before_sl
            pend_sl_time = sh1_time if sh_before_sl == sh1 else None
            pend_break_time = sl1_time
            # Reset recent tracking (new cycle)
            sl_recent_min = sl1
            sh_recent_max = None
            wave_count = 0
            wave1_peak = None
            wave2_peak = None
            in_up_wave = False
            in_down_wave = False
            current_wave_peak = None
            current_wave_trough = None

        # ── Process confirmed signals ──
        if confirmed_buy and pend_break_point is not None and pend_sl is not None:
            entry = pend_break_point  # Entry = break point (sh1)
            sl_buffer = entry * sl_buffer_pct
            sl_buffered = pend_sl - sl_buffer
            risk = entry - sl_buffered
            tp = entry + rr_ratio * risk if rr_ratio > 0 else 0

            if active_signal is not None and active_signal.result == "OPEN":
                active_signal.result = "CLOSE_REVERSE"
                active_signal.pnl_r = _calc_pnl_r(active_signal, bar_close)

            sig = Signal(
                time=bar_time,
                direction="BUY",
                entry=entry,
                sl=sl_buffered,
                tp=tp,
                break_point=pend_break_point,
                break_time=pend_break_time,
                confirm_time=bar_time,
                wave_confirm_time=wave_conf_time,
                result="OPEN",
            )
            signals.append(sig)
            active_signal = sig

        if confirmed_sell and pend_break_point is not None and pend_sl is not None:
            entry = pend_break_point  # Entry = break point (sl1)
            sl_buffer = entry * sl_buffer_pct
            sl_buffered = pend_sl + sl_buffer
            risk = sl_buffered - entry
            tp = entry - rr_ratio * risk if rr_ratio > 0 else 0

            if active_signal is not None and active_signal.result == "OPEN":
                active_signal.result = "CLOSE_REVERSE"
                active_signal.pnl_r = _calc_pnl_r(active_signal, bar_close)

            sig = Signal(
                time=bar_time,
                direction="SELL",
                entry=entry,
                sl=sl_buffered,
                tp=tp,
                break_point=pend_break_point,
                break_time=pend_break_time,
                confirm_time=bar_time,
                wave_confirm_time=wave_conf_time,
                result="OPEN",
            )
            signals.append(sig)
            active_signal = sig

        # ── Check TP/SL hit for active signal ──
        if active_signal is not None and active_signal.result == "OPEN":
            if active_signal.direction == "BUY":
                if bar_low <= active_signal.sl:
                    active_signal.result = "SL"
                    active_signal.pnl_r = -1.0
                    active_signal = None
                elif active_signal.tp > 0 and bar_high >= active_signal.tp:
                    active_signal.result = "TP"
                    active_signal.pnl_r = rr_ratio
                    active_signal = None
            else:  # SELL
                if bar_high >= active_signal.sl:
                    active_signal.result = "SL"
                    active_signal.pnl_r = -1.0
                    active_signal = None
                elif active_signal.tp > 0 and bar_low <= active_signal.tp:
                    active_signal.result = "TP"
                    active_signal.pnl_r = rr_ratio
                    active_signal = None

    return signals, swings


def _calc_pnl_r(signal: Signal, close_price: float) -> float:
    """Calculate P&L in R units."""
    risk = abs(signal.entry - signal.sl)
    if risk == 0:
        return 0
    if signal.direction == "BUY":
        return (close_price - signal.entry) / risk
    else:
        return (signal.entry - close_price) / risk


def signals_to_dataframe(signals: List[Signal]) -> pd.DataFrame:
    """Convert signals to a clean DataFrame for analysis."""
    if not signals:
        return pd.DataFrame()

    records = []
    for s in signals:
        risk = abs(s.entry - s.sl)
        records.append({
            "Time": s.time,
            "Direction": s.direction,
            "Entry": round(s.entry, 5),
            "SL": round(s.sl, 5),
            "TP": round(s.tp, 5) if s.tp > 0 else None,
            "Risk": round(risk, 5),
            "Break Point": round(s.break_point, 5),
            "Break Time": s.break_time,
            "Wave Confirm": s.wave_confirm_time,
            "Confirm Time": s.confirm_time,
            "Result": s.result,
            "PnL (R)": round(s.pnl_r, 2),
        })
    return pd.DataFrame(records)


def print_backtest_summary(signals: List[Signal], rr_ratio: float = 2.0):
    """In kết quả backtest."""
    if not signals:
        print("❌ Không có signal nào.")
        return

    df = signals_to_dataframe(signals)
    closed = df[df["Result"].isin(["TP", "SL", "CLOSE_REVERSE"])]

    total = len(closed)
    if total == 0:
        print(f"📊 Tổng signals: {len(signals)} | Chưa có lệnh nào đóng.")
        return

    wins = len(closed[closed["PnL (R)"] > 0])
    losses = len(closed[closed["PnL (R)"] <= 0])
    tp_hits = len(closed[closed["Result"] == "TP"])
    sl_hits = len(closed[closed["Result"] == "SL"])
    reversed_count = len(closed[closed["Result"] == "CLOSE_REVERSE"])
    win_rate = wins / total * 100 if total > 0 else 0
    total_r = closed["PnL (R)"].sum()
    avg_r = closed["PnL (R)"].mean()

    print("\n" + "=" * 60)
    print(f"📊 BACKTEST SUMMARY — PA Break (RR 1:{rr_ratio})")
    print("=" * 60)
    print(f"  Total signals:    {len(signals)}")
    print(f"  Closed trades:    {total}")
    print(f"  TP hit:           {tp_hits} ({tp_hits/total*100:.1f}%)")
    print(f"  SL hit:           {sl_hits} ({sl_hits/total*100:.1f}%)")
    print(f"  Closed (reverse): {reversed_count}")
    print(f"  Win / Loss:       {wins} / {losses}")
    print(f"  Win Rate:         {win_rate:.1f}%")
    print(f"  Total PnL:        {total_r:.2f} R")
    print(f"  Avg PnL/trade:    {avg_r:.2f} R")

    # Expectancy
    expectancy = win_rate / 100 * rr_ratio - (1 - win_rate / 100)
    print(f"  Expectancy:       {expectancy:.2f} R per trade")
    print("=" * 60)

    # Show BUY vs SELL breakdown
    for direction in ["BUY", "SELL"]:
        sub = closed[closed["Direction"] == direction]
        if len(sub) > 0:
            sub_wins = len(sub[sub["PnL (R)"] > 0])
            sub_wr = sub_wins / len(sub) * 100
            print(f"  {direction}: {len(sub)} trades | "
                  f"WR {sub_wr:.1f}% | "
                  f"PnL {sub['PnL (R)'].sum():.2f} R")


# ── Quick test ──
if __name__ == "__main__":
    from fetch_data import fetch_ohlcv

    # Test với Gold D1
    df = fetch_ohlcv("XAUUSD", "D1", bars=500)
    if not df.empty:
        signals, swings = run_pa_break(df, pivot_len=5, rr_ratio=2.0)
        print(f"\n🔍 Found {len(swings)} swing points")
        print(f"📈 Generated {len(signals)} signals")
        print_backtest_summary(signals, rr_ratio=2.0)

        # Show last 5 signals
        sig_df = signals_to_dataframe(signals)
        if not sig_df.empty:
            print("\n📋 Last 5 signals:")
            print(sig_df.tail().to_string())
