"""
strategy_mst_medio.py — Python backtest for MST Medio v2.0

Logic matches MST Medio.pine v2.0:
1. Find Swing High / Swing Low (pivot)
2. Detect HH (Higher High) / LL (Lower Low) + Impulse Body Filter + Break Strength
3. Find W1 peak: highest high from break candle until first opposing candle
4. Wait for pullback then CLOSE beyond W1 peak → Confirmed! → Signal
5. Entry = old SH (sh0) for BUY, old SL (sl0) for SELL
6. SL = swing opposite before break
7. TP = high of Confirm candle (BUY) or low of Confirm candle (SELL)
"""

__version__ = "v2.0 — Confirm Signal (no retest)"

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Signal:
    time: pd.Timestamp
    direction: str          # "BUY" or "SELL"
    entry: float
    sl: float
    tp: float
    w1_peak: float          # W1 impulse wave peak
    break_time: pd.Timestamp
    confirm_time: pd.Timestamp
    result: str = ""        # "TP", "SL", "CLOSE_REVERSE", "OPEN"
    pnl_r: float = 0.0


@dataclass
class SwingPoint:
    time: pd.Timestamp
    price: float
    type: str               # "HIGH" or "LOW"
    bar_index: int


def find_swings(df: pd.DataFrame, pivot_len: int = 5) -> List[SwingPoint]:
    swings = []
    highs = df["High"].values
    lows = df["Low"].values
    times = df.index

    for i in range(pivot_len, len(df) - pivot_len):
        is_ph = all(highs[i] >= highs[j] for j in range(i - pivot_len, i + pivot_len + 1) if j != i)
        if is_ph:
            swings.append(SwingPoint(time=times[i], price=highs[i], type="HIGH", bar_index=i))

        is_pl = all(lows[i] <= lows[j] for j in range(i - pivot_len, i + pivot_len + 1) if j != i)
        if is_pl:
            swings.append(SwingPoint(time=times[i], price=lows[i], type="LOW", bar_index=i))

    swings.sort(key=lambda s: s.time)
    return swings


def run_mst_medio(
    df: pd.DataFrame,
    pivot_len: int = 5,
    break_mult: float = 0.25,
    impulse_mult: float = 1.5,
    min_rr: float = 0.0,           # Minimum R:R to accept signal (0=no filter)
    sl_buffer_pct: float = 0.0,
    tp_mode: str = "confirm",      # "confirm" = confirm candle H/L, "fixed_rr" = fixed ratio
    fixed_rr: float = 2.0,         # Only used if tp_mode="fixed_rr"
    debug: bool = False,
) -> tuple[List[Signal], List[SwingPoint]]:
    """
    Run MST Medio v2.0 strategy on historical data.
    Signal fires at CONFIRM (close > W1 peak), no retest phase.
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

    # Swing state
    sh1 = sh0 = sl1 = sl0 = None
    sh1_idx = sh0_idx = sl1_idx = sl0_idx = None
    sl_before_sh = None
    sl_before_sh_idx = None
    sh_before_sl = None
    sh_before_sl_idx = None

    # Pending state: 0=idle, 1=waiting confirm BUY, -1=waiting confirm SELL
    pending_state = 0
    pend_break_point = None    # Entry level (sh0 for BUY, sl0 for SELL)
    pend_w1_peak = None        # W1 peak level to confirm against
    pend_w1_trough = None      # W1 trough (low during W1 impulse for BUY, high for SELL)
    pend_sl = None
    pend_sl_idx = None
    pend_break_idx = None

    # Active signal tracking
    active_signal: Optional[Signal] = None

    swing_idx = 0

    for bar_i in range(pivot_len, len(df)):
        bar_time = times[bar_i]
        bar_high = highs[bar_i]
        bar_low = lows[bar_i]
        bar_close = closes[bar_i]
        bar_open = opens[bar_i]

        # Confirmed bar (pivot_len bars ago)
        confirmed_bar = bar_i - pivot_len
        if confirmed_bar < 0:
            continue

        # Check swings at confirmed bar
        is_sw_h = False
        is_sw_l = False

        while swing_idx < len(swings) and swings[swing_idx].bar_index < confirmed_bar:
            swing_idx += 1

        if swing_idx < len(swings) and swings[swing_idx].bar_index == confirmed_bar:
            sw = swings[swing_idx]
            if sw.type == "HIGH": is_sw_h = True
            if sw.type == "LOW": is_sw_l = True
            if swing_idx + 1 < len(swings) and swings[swing_idx + 1].bar_index == confirmed_bar:
                sw2 = swings[swing_idx + 1]
                if sw2.type == "HIGH": is_sw_h = True
                if sw2.type == "LOW": is_sw_l = True

        # Update swing state (matching Pine Script order)
        if is_sw_l:
            sl0, sl0_idx = sl1, sl1_idx
            sl1, sl1_idx = lows[confirmed_bar], confirmed_bar

        if is_sw_h:
            sl_before_sh = sl1
            sl_before_sh_idx = sl1_idx
            sh0, sh0_idx = sh1, sh1_idx
            sh1, sh1_idx = highs[confirmed_bar], confirmed_bar

        if is_sw_l:
            sh_before_sl = sh1
            sh_before_sl_idx = sh1_idx

        # HH / LL Detection
        is_new_hh = is_sw_h and sh0 is not None and sh1 > sh0
        is_new_ll = is_sw_l and sl0 is not None and sl1 < sl0

        # Impulse Body Filter
        if impulse_mult > 0:
            bodies = np.abs(closes[:bar_i+1] - opens[:bar_i+1])
            avg_body = np.mean(bodies[max(0, bar_i-19):bar_i+1]) if bar_i >= 1 else 1.0

            if is_new_hh and sh0_idx is not None:
                found = False
                for j in range(sh0_idx, confirmed_bar + 1):
                    if closes[j] > sh0:
                        found = abs(closes[j] - opens[j]) >= impulse_mult * avg_body
                        break
                if not found:
                    is_new_hh = False

            if is_new_ll and sl0_idx is not None:
                found = False
                for j in range(sl0_idx, confirmed_bar + 1):
                    if closes[j] < sl0:
                        found = abs(closes[j] - opens[j]) >= impulse_mult * avg_body
                        break
                if not found:
                    is_new_ll = False

        # Break Strength Filter
        raw_break_up = False
        raw_break_down = False

        if is_new_hh and sl_before_sh is not None:
            if break_mult <= 0:
                raw_break_up = True
            else:
                sw_range = sh0 - sl_before_sh
                br_dist = sh1 - sh0
                if sw_range > 0 and br_dist >= sw_range * break_mult:
                    raw_break_up = True

        if is_new_ll and sh_before_sl is not None:
            if break_mult <= 0:
                raw_break_down = True
            else:
                sw_range = sh_before_sl - sl0
                br_dist = sl0 - sl1
                if sw_range > 0 and br_dist >= sw_range * break_mult:
                    raw_break_down = True

        # ── Confirmation Logic ──
        confirmed_buy = False
        confirmed_sell = False
        conf_wave_high = 0.0
        conf_wave_low = 0.0

        # Wait for Confirm BUY: close > W1 peak
        if pending_state == 1:
            # Track W1 trough
            if pend_w1_trough is None or bar_low < pend_w1_trough:
                pend_w1_trough = bar_low
            # SL invalidation
            if pend_sl is not None and bar_low <= pend_sl:
                if debug:
                    print(f"  [{bar_time}] ✗ BUY cancelled: SL hit low={bar_low:.2f} <= SL={pend_sl:.2f}")
                pending_state = 0
            # Structure broken: price returns to entry level
            elif pend_break_point is not None and bar_low <= pend_break_point:
                if debug:
                    print(f"  [{bar_time}] ✗ BUY cancelled: returns to entry low={bar_low:.2f} <= entry={pend_break_point:.2f}")
                pending_state = 0
            # Confirm: close > W1 peak
            elif pend_w1_peak is not None and bar_close > pend_w1_peak:
                confirmed_buy = True
                conf_wave_high = bar_high
                conf_wave_low = bar_low
                if debug:
                    print(f"  [{bar_time}] ✓ CONFIRM BUY close={bar_close:.2f} > W1={pend_w1_peak:.2f}")
                pending_state = 0

        # Wait for Confirm SELL: close < W1 trough
        elif pending_state == -1:
            # Track W1 peak (highest high for SELL)
            if pend_w1_trough is None or bar_high > pend_w1_trough:
                pend_w1_trough = bar_high
            # SL invalidation
            if pend_sl is not None and bar_high >= pend_sl:
                if debug:
                    print(f"  [{bar_time}] ✗ SELL cancelled: SL hit high={bar_high:.2f} >= SL={pend_sl:.2f}")
                pending_state = 0
            # Structure broken: price returns to entry level
            elif pend_break_point is not None and bar_high >= pend_break_point:
                if debug:
                    print(f"  [{bar_time}] ✗ SELL cancelled: returns to entry high={bar_high:.2f} >= entry={pend_break_point:.2f}")
                pending_state = 0
            # Confirm: close < W1 trough
            elif pend_w1_peak is not None and bar_close < pend_w1_peak:
                confirmed_sell = True
                conf_wave_high = bar_high
                conf_wave_low = bar_low
                if debug:
                    print(f"  [{bar_time}] ✓ CONFIRM SELL close={bar_close:.2f} < W1={pend_w1_peak:.2f}")
                pending_state = 0

        # ── New break → find W1 peak and start tracking ──
        if raw_break_up:
            if debug:
                print(f"[{bar_time}] BREAK UP sh1={sh1:.2f} sh0={sh0:.2f}")
            # Find W1 peak: highest high from break candle to first bearish candle
            w1_peak = None
            w1_trough_init = None
            found_break = False
            scan_from = sh0_idx if sh0_idx is not None else confirmed_bar

            for j in range(scan_from, bar_i + 1):
                cl = closes[j]
                op = opens[j]
                hi = highs[j]
                lo = lows[j]
                if not found_break:
                    if cl > sh0:
                        found_break = True
                        w1_peak = hi
                        w1_trough_init = lo
                else:
                    if hi > w1_peak:
                        w1_peak = hi
                    if w1_trough_init is None or lo < w1_trough_init:
                        w1_trough_init = lo
                    if cl < op:  # First bearish candle → end of W1
                        break

            if w1_peak is not None:
                pending_state = 1
                pend_break_point = sh0
                pend_w1_peak = w1_peak
                pend_w1_trough = w1_trough_init
                pend_sl = sl_before_sh
                pend_sl_idx = sl_before_sh_idx
                pend_break_idx = sh0_idx

                if debug:
                    print(f"  → Pending BUY, entry={sh0:.2f}, W1={w1_peak:.2f}, SL={pend_sl}")

                # Retroactive scan from W1 end to current bar
                # Find W1 end bar index
                w1_end_j = scan_from
                found_break2 = False
                for j in range(scan_from, bar_i + 1):
                    if not found_break2 and closes[j] > sh0:
                        found_break2 = True
                    elif found_break2 and closes[j] < opens[j]:
                        w1_end_j = j
                        break

                for j in range(w1_end_j + 1, bar_i + 1):
                    rH, rL, rC = highs[j], lows[j], closes[j]
                    if pending_state == 1:
                        if pend_w1_trough is None or rL < pend_w1_trough:
                            pend_w1_trough = rL
                        if pend_sl is not None and rL <= pend_sl:
                            pending_state = 0
                            break
                        if rL <= pend_break_point:
                            pending_state = 0
                            break
                        if rC > pend_w1_peak:
                            confirmed_buy = True
                            conf_wave_high = rH
                            conf_wave_low = rL
                            if debug:
                                print(f"  retro[{times[j]}] ✓ CONFIRM BUY close={rC:.2f} > W1={pend_w1_peak:.2f}")
                            pending_state = 0
                            break
                    if pending_state == 0:
                        break

        if raw_break_down:
            if debug:
                print(f"[{bar_time}] BREAK DOWN sl1={sl1:.2f} sl0={sl0:.2f}")
            # Find W1 trough: lowest low from break candle to first bullish candle
            w1_trough = None
            w1_peak_init = None
            found_break = False
            scan_from = sl0_idx if sl0_idx is not None else confirmed_bar

            for j in range(scan_from, bar_i + 1):
                cl = closes[j]
                op = opens[j]
                hi = highs[j]
                lo = lows[j]
                if not found_break:
                    if cl < sl0:
                        found_break = True
                        w1_trough = lo
                        w1_peak_init = hi
                else:
                    if lo < w1_trough:
                        w1_trough = lo
                    if w1_peak_init is None or hi > w1_peak_init:
                        w1_peak_init = hi
                    if cl > op:  # First bullish candle → end of W1
                        break

            if w1_trough is not None:
                pending_state = -1
                pend_break_point = sl0
                pend_w1_peak = w1_trough  # Level to break below (confirm)
                pend_w1_trough = w1_peak_init
                pend_sl = sh_before_sl
                pend_sl_idx = sh_before_sl_idx
                pend_break_idx = sl0_idx

                if debug:
                    print(f"  → Pending SELL, entry={sl0:.2f}, W1={w1_trough:.2f}, SL={pend_sl}")

                # Retroactive scan
                w1_end_j = scan_from
                found_break2 = False
                for j in range(scan_from, bar_i + 1):
                    if not found_break2 and closes[j] < sl0:
                        found_break2 = True
                    elif found_break2 and closes[j] > opens[j]:
                        w1_end_j = j
                        break

                for j in range(w1_end_j + 1, bar_i + 1):
                    rH, rL, rC = highs[j], lows[j], closes[j]
                    if pending_state == -1:
                        if pend_w1_trough is None or rH > pend_w1_trough:
                            pend_w1_trough = rH
                        if pend_sl is not None and rH >= pend_sl:
                            pending_state = 0
                            break
                        if rH >= pend_break_point:
                            pending_state = 0
                            break
                        if rC < pend_w1_peak:
                            confirmed_sell = True
                            conf_wave_high = rH
                            conf_wave_low = rL
                            if debug:
                                print(f"  retro[{times[j]}] ✓ CONFIRM SELL close={rC:.2f} < W1={pend_w1_peak:.2f}")
                            pending_state = 0
                            break
                    if pending_state == 0:
                        break

        # ── Process confirmed signals ──
        if confirmed_buy and pend_break_point is not None and pend_sl is not None:
            entry = pend_break_point
            sl_val = pend_sl - entry * sl_buffer_pct if sl_buffer_pct > 0 else pend_sl
            risk = abs(entry - sl_val)

            if tp_mode == "confirm":
                tp = conf_wave_high  # TP = high of confirm candle
            else:
                tp = entry + fixed_rr * risk if risk > 0 else 0

            # R:R check
            reward = abs(tp - entry) if tp > 0 else 0
            rr = reward / risk if risk > 0 else 0

            if min_rr > 0 and rr < min_rr:
                if debug:
                    print(f"  ⚠️ Skipped BUY: R:R={rr:.2f} < min={min_rr:.1f}")
            else:
                if active_signal is not None and active_signal.result == "OPEN":
                    active_signal.result = "CLOSE_REVERSE"
                    active_signal.pnl_r = _calc_pnl_r(active_signal, bar_close)

                sig = Signal(
                    time=bar_time, direction="BUY", entry=entry, sl=sl_val, tp=tp,
                    w1_peak=pend_w1_peak, break_time=times[pend_break_idx] if pend_break_idx else bar_time,
                    confirm_time=bar_time, result="OPEN",
                )
                signals.append(sig)
                active_signal = sig

        if confirmed_sell and pend_break_point is not None and pend_sl is not None:
            entry = pend_break_point
            sl_val = pend_sl + entry * sl_buffer_pct if sl_buffer_pct > 0 else pend_sl
            risk = abs(sl_val - entry)

            if tp_mode == "confirm":
                tp = conf_wave_low  # TP = low of confirm candle
            else:
                tp = entry - fixed_rr * risk if risk > 0 else 0

            # R:R check
            reward = abs(entry - tp) if tp > 0 else 0
            rr = reward / risk if risk > 0 else 0

            if min_rr > 0 and rr < min_rr:
                if debug:
                    print(f"  ⚠️ Skipped SELL: R:R={rr:.2f} < min={min_rr:.1f}")
            else:
                if active_signal is not None and active_signal.result == "OPEN":
                    active_signal.result = "CLOSE_REVERSE"
                    active_signal.pnl_r = _calc_pnl_r(active_signal, bar_close)

                sig = Signal(
                    time=bar_time, direction="SELL", entry=entry, sl=sl_val, tp=tp,
                    w1_peak=pend_w1_peak, break_time=times[pend_break_idx] if pend_break_idx else bar_time,
                    confirm_time=bar_time, result="OPEN",
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
                    rr_actual = abs(active_signal.tp - active_signal.entry) / abs(active_signal.entry - active_signal.sl)
                    active_signal.result = "TP"
                    active_signal.pnl_r = rr_actual
                    active_signal = None
            else:
                if bar_high >= active_signal.sl:
                    active_signal.result = "SL"
                    active_signal.pnl_r = -1.0
                    active_signal = None
                elif active_signal.tp > 0 and bar_low <= active_signal.tp:
                    rr_actual = abs(active_signal.entry - active_signal.tp) / abs(active_signal.sl - active_signal.entry)
                    active_signal.result = "TP"
                    active_signal.pnl_r = rr_actual
                    active_signal = None

    return signals, swings


def _calc_pnl_r(signal: Signal, close_price: float) -> float:
    risk = abs(signal.entry - signal.sl)
    if risk == 0:
        return 0
    if signal.direction == "BUY":
        return (close_price - signal.entry) / risk
    else:
        return (signal.entry - close_price) / risk


def signals_to_dataframe(signals: List[Signal]) -> pd.DataFrame:
    if not signals:
        return pd.DataFrame()
    records = []
    fmt = "%Y-%m-%d %H:%M"
    for s in signals:
        risk = abs(s.entry - s.sl)
        reward = abs(s.tp - s.entry) if s.tp > 0 else 0
        rr = reward / risk if risk > 0 else 0
        records.append({
            "Time": s.time.strftime(fmt),
            "Dir": s.direction,
            "Entry": round(s.entry, 2),
            "SL": round(s.sl, 2),
            "TP": round(s.tp, 2),
            "R:R": round(rr, 2),
            "W1 Peak": round(s.w1_peak, 2),
            "Result": s.result,
            "PnL(R)": round(s.pnl_r, 2),
        })
    return pd.DataFrame(records)


def print_summary(signals: List[Signal], title: str = "MST Medio v2.0"):
    if not signals:
        print("No signals found.")
        return

    df = signals_to_dataframe(signals)
    closed = df[df["Result"].isin(["TP", "SL", "CLOSE_REVERSE"])]
    total = len(closed)

    if total == 0:
        print(f"Signals: {len(signals)} | None closed yet.")
        return

    wins = len(closed[closed["PnL(R)"] > 0])
    tp_hits = len(closed[closed["Result"] == "TP"])
    sl_hits = len(closed[closed["Result"] == "SL"])
    rev = len(closed[closed["Result"] == "CLOSE_REVERSE"])
    wr = wins / total * 100
    total_r = closed["PnL(R)"].sum()
    avg_rr = closed.loc[closed["PnL(R)"] > 0, "PnL(R)"].mean() if wins > 0 else 0

    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")
    print(f"  Signals: {len(signals)} | Closed: {total}")
    print(f"  TP: {tp_hits} | SL: {sl_hits} | Reversed: {rev}")
    print(f"  Win Rate: {wr:.1f}% ({wins}/{total})")
    print(f"  Total PnL: {total_r:+.2f} R")
    print(f"  Avg Win: {avg_rr:.2f} R | Avg Trade: {total_r/total:.2f} R")
    print(f"{'='*60}")

    for d in ["BUY", "SELL"]:
        sub = closed[closed["Dir"] == d]
        if len(sub) > 0:
            w = len(sub[sub["PnL(R)"] > 0])
            print(f"  {d}: {len(sub)} trades | WR {w/len(sub)*100:.1f}% | PnL {sub['PnL(R)'].sum():+.2f} R")

    print(f"\n{df.to_string(index=False)}")
