# indie:lang_version = 5
# ─────────────────────────────────────────────────────────────────────────────
# Indicator : MST Medio (Make Simple Trading by Medio)
# Version   : v1.4 (Indie)
# Author    : Tuan
# Purpose   : 2-Step Breakout Confirmation System
#             1. Detect HH/LL breakout (with impulse body filter)
#             2. Find W1 Peak (first impulse wave extreme after break)
#             3. Wait for CLOSE beyond W1 Peak → Confirmed! → Signal
#             4. Entry = old SH/SL, SL = swing opposite
#             5. TP = Confirm Break candle H/L (W1 Peak area)
# Notes     : Converted from Pine Script v6. Works on all timeframes.
#             HTF trend notes omitted (Indie calc_on() limitation).
# ─────────────────────────────────────────────────────────────────────────────

from indie import indicator, MainContext, Var, param, color, line_style
from indie.drawings import (
    LineSegment, LabelAbs, Rectangle, AbsolutePosition,
    callout_position,
)
from indie.color import rgba
from math import isnan, nan


# ============================================================================
# MAIN INDICATOR
# ============================================================================
@indicator('MST Medio', overlay_main_pane=True)
@param.int('pivot_len', default=5, min=2, max=50, title='Pivot Lookback')
@param.float('break_mult', default=0.25, min=0.0, max=10.0, step=0.25, title='Break Strength')
@param.float('impulse_mult', default=1.0, min=0.0, max=10.0, step=0.25, title='Impulse Body Filter')
@param.bool('show_swings', default=False, title='Show Swing Points')
@param.bool('show_break_label', default=True, title='Show Confirm Break Label')
@param.bool('show_break_line', default=True, title='Show Entry / SL / TP Lines')
@param.bool('show_boxes', default=True, title='Show Risk/Reward Zones')
@param.bool('show_pending', default=True, title='Show Pending State')
@param.color('col_break_up', default=rgba(38, 166, 154, 1.0), title='Break UP Color')
@param.color('col_break_down', default=rgba(239, 83, 80, 1.0), title='Break DOWN Color')
@param.color('col_entry_buy', default=rgba(33, 150, 243, 1.0), title='Entry Buy Color')
@param.color('col_entry_sell', default=rgba(255, 105, 180, 1.0), title='Entry Sell Color')
@param.color('col_sl', default=rgba(255, 152, 0, 1.0), title='Stop Loss Color')
@param.color('col_tp', default=rgba(76, 175, 80, 1.0), title='Take Profit Color')
@param.color('col_swing_high', default=rgba(255, 165, 0, 0.6), title='Swing High Color')
@param.color('col_swing_low', default=rgba(0, 0, 255, 0.6), title='Swing Low Color')
class Main(MainContext):
    def calc(
        self,
        pivot_len, break_mult, impulse_mult,
        show_swings, show_break_label, show_break_line, show_boxes, show_pending,
        col_break_up, col_break_down, col_entry_buy, col_entry_sell,
        col_sl, col_tp, col_swing_high, col_swing_low,
    ):
        pl: int = pivot_len

        # ========================================================================
        # PERSISTENT STATE (Var[T].new() auto-persists across bars via sugar)
        # ========================================================================
        # -- Swing History --
        sh1 = Var[float].new(nan)       # Most recent Swing High
        sh0 = Var[float].new(nan)       # Previous Swing High
        sh1_idx = Var[int].new(-1)
        sh0_idx = Var[int].new(-1)
        sh1_time = Var[float].new(nan)
        sh0_time = Var[float].new(nan)

        sl1 = Var[float].new(nan)       # Most recent Swing Low
        sl0 = Var[float].new(nan)       # Previous Swing Low
        sl1_idx = Var[int].new(-1)
        sl0_idx = Var[int].new(-1)
        sl1_time = Var[float].new(nan)
        sl0_time = Var[float].new(nan)

        sl_before_sh = Var[float].new(nan)
        sl_before_sh_idx = Var[int].new(-1)
        sl_before_sh_time = Var[float].new(nan)
        sh_before_sl = Var[float].new(nan)
        sh_before_sl_idx = Var[int].new(-1)
        sh_before_sl_time = Var[float].new(nan)

        # -- Pending State --
        pending_state = Var[int].new(0)
        pend_break_point = Var[float].new(nan)
        pend_w1_peak = Var[float].new(nan)
        pend_w1_trough = Var[float].new(nan)
        pend_sl = Var[float].new(nan)
        pend_sl_idx = Var[int].new(-1)
        pend_sl_time = Var[float].new(nan)
        pend_break_idx = Var[int].new(-1)
        pend_break_time = Var[float].new(nan)

        # -- Active signal state --
        active_entry_price = Var[float].new(nan)
        active_tp_price = Var[float].new(nan)
        active_signal_dir = Var[int].new(0)

        # -- Pending drawings (track previous to erase) --
        # Indie Var[T] requires init value of type T, no None allowed.
        # Use invisible dummy objects as sentinels, and a flag to track validity.
        _dummy_pos: AbsolutePosition = AbsolutePosition(0.0, 0.0)
        _dummy_line: LineSegment = LineSegment(_dummy_pos, _dummy_pos, color=rgba(0, 0, 0, 0.0))
        _dummy_label: LabelAbs = LabelAbs('', _dummy_pos, text_color=rgba(0, 0, 0, 0.0), bg_color=rgba(0, 0, 0, 0.0))
        prev_pend_entry = Var[LineSegment].new(_dummy_line)
        prev_pend_w1 = Var[LineSegment].new(_dummy_line)
        prev_pend_sl_draw = Var[LineSegment].new(_dummy_line)
        prev_pend_label = Var[LabelAbs].new(_dummy_label)
        has_pend_drawings = Var[int].new(0)  # 0=no drawings, 1=has drawings

        # ========================================================================
        # SWING DETECTION (manual pivot high/low)
        # ========================================================================
        swing_high: float = nan
        swing_low: float = nan

        # Need at least pl bars on each side
        if self.bar_index >= pl * 2:
            # Check if bar at offset pl is a swing high
            candidate_h: float = self.high[pl]
            is_pivot_h: bool = True
            for k in range(0, pl * 2 + 1):
                if k == pl:
                    continue
                if self.high[k] > candidate_h:
                    is_pivot_h = False
                    break
            if is_pivot_h:
                swing_high = candidate_h

            # Check if bar at offset pl is a swing low
            candidate_l: float = self.low[pl]
            is_pivot_l: bool = True
            for k in range(0, pl * 2 + 1):
                if k == pl:
                    continue
                if self.low[k] < candidate_l:
                    is_pivot_l = False
                    break
            if is_pivot_l:
                swing_low = candidate_l

        # ========================================================================
        # TRACK SWING HISTORY
        # ========================================================================
        if not isnan(swing_low):
            sl0.set(sl1.get())
            sl0_idx.set(sl1_idx.get())
            sl0_time.set(sl1_time.get())
            sl1.set(swing_low)
            sl1_idx.set(self.bar_index - pl)
            sl1_time.set(self.time[pl])

        if not isnan(swing_high):
            sl_before_sh.set(sl1.get())
            sl_before_sh_idx.set(sl1_idx.get())
            sl_before_sh_time.set(sl1_time.get())
            sh0.set(sh1.get())
            sh0_idx.set(sh1_idx.get())
            sh0_time.set(sh1_time.get())
            sh1.set(swing_high)
            sh1_idx.set(self.bar_index - pl)
            sh1_time.set(self.time[pl])

        if not isnan(swing_low):
            sh_before_sl.set(sh1.get())
            sh_before_sl_idx.set(sh1_idx.get())
            sh_before_sl_time.set(sh1_time.get())

        # ========================================================================
        # HH / LL DETECTION
        # ========================================================================
        is_new_hh: bool = (not isnan(swing_high)
                           and not isnan(sh0.get())
                           and sh1.get() > sh0.get())
        is_new_ll: bool = (not isnan(swing_low)
                           and not isnan(sl0.get())
                           and sl1.get() < sl0.get())

        # ========================================================================
        # IMPULSE BODY FILTER
        # ========================================================================
        avg_body: float = _calc_avg_body(self, 20)

        if is_new_hh and impulse_mult > 0:
            from_bar: int = self.bar_index - sh0_idx.get()
            to_bar: int = pl
            found: bool = False
            i: int = from_bar
            while i >= to_bar:
                if self.close[i] > sh0.get():
                    found = abs(self.close[i] - self.open[i]) >= impulse_mult * avg_body
                    break
                i -= 1
            if not found:
                is_new_hh = False

        if is_new_ll and impulse_mult > 0:
            from_bar_d: int = self.bar_index - sl0_idx.get()
            to_bar_d: int = pl
            found_d: bool = False
            i2: int = from_bar_d
            while i2 >= to_bar_d:
                if self.close[i2] < sl0.get():
                    found_d = abs(self.close[i2] - self.open[i2]) >= impulse_mult * avg_body
                    break
                i2 -= 1
            if not found_d:
                is_new_ll = False

        # ========================================================================
        # BREAK STRENGTH FILTER
        # ========================================================================
        raw_break_up: bool = False
        raw_break_down: bool = False

        if is_new_hh and not isnan(sl_before_sh.get()):
            if break_mult <= 0:
                raw_break_up = True
            else:
                sw_r: float = sh0.get() - sl_before_sh.get()
                br_d: float = sh1.get() - sh0.get()
                if sw_r > 0 and br_d >= sw_r * break_mult:
                    raw_break_up = True

        if is_new_ll and not isnan(sh_before_sl.get()):
            if break_mult <= 0:
                raw_break_down = True
            else:
                sw_r2: float = sh_before_sl.get() - sl0.get()
                br_d2: float = sl0.get() - sl1.get()
                if sw_r2 > 0 and br_d2 >= sw_r2 * break_mult:
                    raw_break_down = True

        # ========================================================================
        # SWING POINT VISUALIZATION
        # ========================================================================
        if show_swings and not isnan(swing_high):
            self.chart.draw(LabelAbs(
                '▼',
                AbsolutePosition(self.time[pl], self.high[pl]),
                text_color=col_swing_high,
                bg_color=rgba(0, 0, 0, 0.0),
                font_size=10,
                callout_position=callout_position.BOTTOM_LEFT,
            ))

        if show_swings and not isnan(swing_low):
            self.chart.draw(LabelAbs(
                '▲',
                AbsolutePosition(self.time[pl], self.low[pl]),
                text_color=col_swing_low,
                bg_color=rgba(0, 0, 0, 0.0),
                font_size=10,
                callout_position=callout_position.TOP_LEFT,
            ))

        # ========================================================================
        # CONFIRMED SIGNALS (track state)
        # ========================================================================
        confirmed_buy: bool = False
        confirmed_sell: bool = False
        conf_entry: float = nan
        conf_sl_val: float = nan
        conf_sl_time: float = nan
        conf_break_time: float = nan
        conf_w1_peak: float = nan
        conf_wave_bar: int = -1
        conf_wave_time: float = nan
        conf_wave_high: float = nan
        conf_wave_low: float = nan

        # ========================================================================
        # POST-SIGNAL ENTRY TOUCH → TERMINATE LINES
        # ========================================================================
        if not isnan(active_entry_price.get()) and active_signal_dir.get() != 0:
            touch_entry: bool = False
            if active_signal_dir.get() == 1 and self.low[0] <= active_entry_price.get():
                touch_entry = True
            elif active_signal_dir.get() == -1 and self.high[0] >= active_entry_price.get():
                touch_entry = True
            if touch_entry:
                active_entry_price.set(nan)
                active_tp_price.set(nan)
                active_signal_dir.set(0)

        # ========================================================================
        # WAIT FOR CONFIRM: CLOSE > W1 PEAK (BUY) or CLOSE < W1 TROUGH (SELL)
        # ========================================================================
        ps: int = pending_state.get()

        if ps == 1:
            # BUY: wait for close > W1 peak
            if isnan(pend_w1_trough.get()) or self.low[0] < pend_w1_trough.get():
                pend_w1_trough.set(self.low[0])
            if not isnan(pend_sl.get()) and self.low[0] <= pend_sl.get():
                pending_state.set(0)
            elif not isnan(pend_break_point.get()) and self.low[0] <= pend_break_point.get():
                pending_state.set(0)
            elif not isnan(pend_w1_peak.get()) and self.close[0] > pend_w1_peak.get():
                confirmed_buy = True
                conf_entry = pend_break_point.get()
                conf_sl_val = pend_sl.get()
                conf_sl_time = pend_sl_time.get()
                conf_break_time = pend_break_time.get()
                conf_w1_peak = pend_w1_peak.get()
                conf_wave_bar = self.bar_index
                conf_wave_time = self.time[0]
                conf_wave_high = self.high[0]
                conf_wave_low = self.low[0]
                pending_state.set(0)

        if ps == -1:
            # SELL: wait for close < W1 trough
            if isnan(pend_w1_trough.get()) or self.high[0] > pend_w1_trough.get():
                pend_w1_trough.set(self.high[0])
            if not isnan(pend_sl.get()) and self.high[0] >= pend_sl.get():
                pending_state.set(0)
            elif not isnan(pend_break_point.get()) and self.high[0] >= pend_break_point.get():
                pending_state.set(0)
            elif not isnan(pend_w1_peak.get()) and self.close[0] < pend_w1_peak.get():
                confirmed_sell = True
                conf_entry = pend_break_point.get()
                conf_sl_val = pend_sl.get()
                conf_sl_time = pend_sl_time.get()
                conf_break_time = pend_break_time.get()
                conf_w1_peak = pend_w1_peak.get()
                conf_wave_bar = self.bar_index
                conf_wave_time = self.time[0]
                conf_wave_high = self.high[0]
                conf_wave_low = self.low[0]
                pending_state.set(0)

        # ========================================================================
        # NEW RAW BREAK UP → START TRACKING
        # ========================================================================
        if raw_break_up:
            active_entry_price.set(nan)
            active_tp_price.set(nan)
            active_signal_dir.set(0)

            # Find W1 peak: highest high from break candle until first bearish
            w1_peak: float = nan
            w1_lookback: int = -1
            w1_trough_init: float = nan
            found_break: bool = False
            scan_from: int = self.bar_index - sh0_idx.get()

            i3: int = scan_from
            while i3 >= 0:
                cl: float = self.close[i3]
                op: float = self.open[i3]
                hi: float = self.high[i3]
                lo: float = self.low[i3]
                if not found_break:
                    if cl > sh0.get():
                        found_break = True
                        w1_peak = hi
                        w1_lookback = i3
                        w1_trough_init = lo
                else:
                    if hi > w1_peak:
                        w1_peak = hi
                        w1_lookback = i3
                    if isnan(w1_trough_init) or lo < w1_trough_init:
                        w1_trough_init = lo
                    if cl < op:  # First bearish → end of W1 impulse
                        break
                i3 -= 1

            if not isnan(w1_peak):
                pending_state.set(1)
                pend_break_point.set(sh0.get())
                pend_w1_peak.set(w1_peak)
                pend_w1_trough.set(w1_trough_init)
                pend_sl.set(sl_before_sh.get())
                pend_sl_idx.set(sl_before_sh_idx.get())
                pend_sl_time.set(sl_before_sh_time.get())
                pend_break_idx.set(sh0_idx.get())
                pend_break_time.set(sh0_time.get())

                # Retroactive scan
                retro_from: int = max(w1_lookback - 1, 0)
                ri: int = retro_from
                while ri >= 0:
                    r_high: float = self.high[ri]
                    r_low: float = self.low[ri]
                    r_close: float = self.close[ri]
                    cur_ps: int = pending_state.get()
                    if cur_ps == 1:
                        if isnan(pend_w1_trough.get()) or r_low < pend_w1_trough.get():
                            pend_w1_trough.set(r_low)
                        if not isnan(pend_sl.get()) and r_low <= pend_sl.get():
                            pending_state.set(0)
                            break
                        if r_low <= pend_break_point.get():
                            pending_state.set(0)
                            break
                        if r_close > pend_w1_peak.get():
                            confirmed_buy = True
                            conf_entry = pend_break_point.get()
                            conf_sl_val = pend_sl.get()
                            conf_sl_time = pend_sl_time.get()
                            conf_break_time = pend_break_time.get()
                            conf_w1_peak = pend_w1_peak.get()
                            conf_wave_bar = self.bar_index - ri
                            conf_wave_time = self.time[ri]
                            conf_wave_high = r_high
                            conf_wave_low = r_low
                            pending_state.set(0)
                            break
                    if pending_state.get() == 0:
                        break
                    ri -= 1

        # ========================================================================
        # NEW RAW BREAK DOWN → START TRACKING
        # ========================================================================
        if raw_break_down:
            active_entry_price.set(nan)
            active_tp_price.set(nan)
            active_signal_dir.set(0)

            # Find W1 trough: lowest low from break candle until first bullish
            w1_trough_s: float = nan
            w1_lb_sell: int = -1
            w1_trough_init_s: float = nan
            found_brk_dn: bool = False
            scan_from_dn: int = self.bar_index - sl0_idx.get()

            i4: int = scan_from_dn
            while i4 >= 0:
                cl_s: float = self.close[i4]
                op_s: float = self.open[i4]
                lo_s: float = self.low[i4]
                hi_s: float = self.high[i4]
                if not found_brk_dn:
                    if cl_s < sl0.get():
                        found_brk_dn = True
                        w1_trough_s = lo_s
                        w1_lb_sell = i4
                        w1_trough_init_s = hi_s
                else:
                    if lo_s < w1_trough_s:
                        w1_trough_s = lo_s
                        w1_lb_sell = i4
                    if isnan(w1_trough_init_s) or hi_s > w1_trough_init_s:
                        w1_trough_init_s = hi_s
                    if cl_s > op_s:  # First bullish → end of W1 impulse
                        break
                i4 -= 1

            if not isnan(w1_trough_s):
                pending_state.set(-1)
                pend_break_point.set(sl0.get())
                pend_w1_peak.set(w1_trough_s)
                pend_w1_trough.set(w1_trough_init_s)
                pend_sl.set(sh_before_sl.get())
                pend_sl_idx.set(sh_before_sl_idx.get())
                pend_sl_time.set(sh_before_sl_time.get())
                pend_break_idx.set(sl0_idx.get())
                pend_break_time.set(sl0_time.get())

                # Retroactive scan
                retro_from_s: int = max(w1_lb_sell - 1, 0)
                ri2: int = retro_from_s
                while ri2 >= 0:
                    r_high_s: float = self.high[ri2]
                    r_low_s: float = self.low[ri2]
                    r_close_s: float = self.close[ri2]
                    cur_ps2: int = pending_state.get()
                    if cur_ps2 == -1:
                        if isnan(pend_w1_trough.get()) or r_high_s > pend_w1_trough.get():
                            pend_w1_trough.set(r_high_s)
                        if not isnan(pend_sl.get()) and r_high_s >= pend_sl.get():
                            pending_state.set(0)
                            break
                        if r_high_s >= pend_break_point.get():
                            pending_state.set(0)
                            break
                        if r_close_s < pend_w1_peak.get():
                            confirmed_sell = True
                            conf_entry = pend_break_point.get()
                            conf_sl_val = pend_sl.get()
                            conf_sl_time = pend_sl_time.get()
                            conf_break_time = pend_break_time.get()
                            conf_w1_peak = pend_w1_peak.get()
                            conf_wave_bar = self.bar_index - ri2
                            conf_wave_time = self.time[ri2]
                            conf_wave_high = r_high_s
                            conf_wave_low = r_low_s
                            pending_state.set(0)
                            break
                    if pending_state.get() == 0:
                        break
                    ri2 -= 1

        # ========================================================================
        # DRAW CONFIRMED BUY
        # ========================================================================
        if confirmed_buy:
            tp_val: float = conf_wave_high
            risk: float = abs(conf_entry - conf_sl_val)
            reward: float = abs(tp_val - conf_entry)
            rr: float = reward / risk if risk > 0 else 0.0

            if show_break_line:
                # Entry line
                self.chart.draw(LineSegment(
                    AbsolutePosition(conf_break_time, conf_entry),
                    AbsolutePosition(self.time[0], conf_entry),
                    color=col_entry_buy,
                    line_style=line_style.DASHED, line_width=1,
                ))
                # SL line
                self.chart.draw(LineSegment(
                    AbsolutePosition(conf_sl_time, conf_sl_val),
                    AbsolutePosition(self.time[0], conf_sl_val),
                    color=col_sl,
                    line_style=line_style.DASHED, line_width=1,
                ))
                # TP line
                self.chart.draw(LineSegment(
                    AbsolutePosition(conf_break_time, tp_val),
                    AbsolutePosition(self.time[0], tp_val),
                    color=col_tp,
                    line_style=line_style.DASHED, line_width=1,
                ))

                # Labels
                self.chart.draw(LabelAbs(
                    'Entry',
                    AbsolutePosition(self.time[0], conf_entry),
                    bg_color=col_entry_buy, text_color=color.WHITE,
                    font_size=11, callout_position=callout_position.TOP_LEFT,
                ))
                self.chart.draw(LabelAbs(
                    'SL',
                    AbsolutePosition(self.time[0], conf_sl_val),
                    bg_color=col_sl, text_color=color.WHITE,
                    font_size=9, callout_position=callout_position.TOP_LEFT,
                ))
                rr_text: str = 'TP (' + str(round(rr, 1)) + 'R)'
                self.chart.draw(LabelAbs(
                    rr_text,
                    AbsolutePosition(self.time[0], tp_val),
                    bg_color=col_tp, text_color=color.WHITE,
                    font_size=9, callout_position=callout_position.TOP_LEFT,
                ))

            if show_boxes:
                self.chart.draw(Rectangle(
                    AbsolutePosition(conf_break_time, conf_entry),
                    AbsolutePosition(self.time[0], conf_sl_val),
                    line_color=col_sl(0.4), bg_color=col_sl(0.1), line_width=0,
                ))
                self.chart.draw(Rectangle(
                    AbsolutePosition(conf_break_time, tp_val),
                    AbsolutePosition(self.time[0], conf_entry),
                    line_color=col_tp(0.4), bg_color=col_tp(0.1), line_width=0,
                ))

            if show_break_label:
                self.chart.draw(LabelAbs(
                    '▲ Confirm Break',
                    AbsolutePosition(conf_wave_time, conf_wave_high),
                    bg_color=col_break_up, text_color=color.WHITE,
                    font_size=9, callout_position=callout_position.BOTTOM_LEFT,
                ))

        # ========================================================================
        # DRAW CONFIRMED SELL
        # ========================================================================
        if confirmed_sell:
            tp_val_s: float = conf_wave_low
            risk_s: float = abs(conf_sl_val - conf_entry)
            reward_s: float = abs(conf_entry - tp_val_s)
            rr_s: float = reward_s / risk_s if risk_s > 0 else 0.0

            if show_break_line:
                # Entry line
                self.chart.draw(LineSegment(
                    AbsolutePosition(conf_break_time, conf_entry),
                    AbsolutePosition(self.time[0], conf_entry),
                    color=col_entry_sell,
                    line_style=line_style.DASHED, line_width=1,
                ))
                # SL line
                self.chart.draw(LineSegment(
                    AbsolutePosition(conf_sl_time, conf_sl_val),
                    AbsolutePosition(self.time[0], conf_sl_val),
                    color=col_sl,
                    line_style=line_style.DASHED, line_width=1,
                ))
                # TP line
                self.chart.draw(LineSegment(
                    AbsolutePosition(conf_break_time, tp_val_s),
                    AbsolutePosition(self.time[0], tp_val_s),
                    color=col_tp,
                    line_style=line_style.DASHED, line_width=1,
                ))

                # Labels
                self.chart.draw(LabelAbs(
                    'Entry',
                    AbsolutePosition(self.time[0], conf_entry),
                    bg_color=col_entry_sell, text_color=color.WHITE,
                    font_size=11, callout_position=callout_position.TOP_LEFT,
                ))
                self.chart.draw(LabelAbs(
                    'SL',
                    AbsolutePosition(self.time[0], conf_sl_val),
                    bg_color=col_sl, text_color=color.WHITE,
                    font_size=9, callout_position=callout_position.TOP_LEFT,
                ))
                rr_text_s: str = 'TP (' + str(round(rr_s, 1)) + 'R)'
                self.chart.draw(LabelAbs(
                    rr_text_s,
                    AbsolutePosition(self.time[0], tp_val_s),
                    bg_color=col_tp, text_color=color.WHITE,
                    font_size=9, callout_position=callout_position.TOP_LEFT,
                ))

            if show_boxes:
                self.chart.draw(Rectangle(
                    AbsolutePosition(conf_break_time, conf_sl_val),
                    AbsolutePosition(self.time[0], conf_entry),
                    line_color=col_sl(0.4), bg_color=col_sl(0.1), line_width=0,
                ))
                self.chart.draw(Rectangle(
                    AbsolutePosition(conf_break_time, conf_entry),
                    AbsolutePosition(self.time[0], tp_val_s),
                    line_color=col_tp(0.4), bg_color=col_tp(0.1), line_width=0,
                ))

            if show_break_label:
                self.chart.draw(LabelAbs(
                    '▼ Confirm Break',
                    AbsolutePosition(conf_wave_time, conf_wave_low),
                    bg_color=col_break_down, text_color=color.WHITE,
                    font_size=9, callout_position=callout_position.TOP_LEFT,
                ))

        # ========================================================================
        # PENDING STATE VISUALIZATION
        # ========================================================================
        cur_pending: int = pending_state.get()

        # Erase previous pending drawings if they exist
        if has_pend_drawings.get() == 1:
            self.chart.erase(prev_pend_entry.get())
            self.chart.erase(prev_pend_w1.get())
            self.chart.erase(prev_pend_sl_draw.get())
            self.chart.erase(prev_pend_label.get())
            has_pend_drawings.set(0)

        if show_pending and cur_pending != 0:
            is_buy_pend: bool = cur_pending > 0
            pend_color = col_entry_buy(0.5) if is_buy_pend else col_entry_sell(0.5)
            w1_color = col_tp(0.5)

            # Entry level line (dotted)
            bp: float = pend_break_point.get()
            bt: float = pend_break_time.get()
            if not isnan(bp) and not isnan(bt):
                pel: LineSegment = LineSegment(
                    AbsolutePosition(bt, bp),
                    AbsolutePosition(self.time[0], bp),
                    color=pend_color,
                    line_style=line_style.DOTTED, line_width=1,
                )
                self.chart.draw(pel)
                prev_pend_entry.set(pel)

            # W1 Peak/Trough line (dotted)
            wp: float = pend_w1_peak.get()
            if not isnan(wp):
                w1_start_t: float = bt if not isnan(bt) else self.time[min(20, self.bar_index)]
                pwl: LineSegment = LineSegment(
                    AbsolutePosition(w1_start_t, wp),
                    AbsolutePosition(self.time[0], wp),
                    color=w1_color,
                    line_style=line_style.DOTTED, line_width=1,
                )
                self.chart.draw(pwl)
                prev_pend_w1.set(pwl)

            # SL line (dotted)
            psl_val: float = pend_sl.get()
            psl_t: float = pend_sl_time.get()
            if not isnan(psl_val) and not isnan(psl_t):
                psl_draw: LineSegment = LineSegment(
                    AbsolutePosition(psl_t, psl_val),
                    AbsolutePosition(self.time[0], psl_val),
                    color=col_sl(0.5),
                    line_style=line_style.DOTTED, line_width=1,
                )
                self.chart.draw(psl_draw)
                prev_pend_sl_draw.set(psl_draw)

            # Pending label
            pend_text: str = 'Pending BUY' if is_buy_pend else 'Pending SELL'
            cp_pos = callout_position.TOP_LEFT if is_buy_pend else callout_position.BOTTOM_LEFT
            ppl: LabelAbs = LabelAbs(
                pend_text,
                AbsolutePosition(self.time[0], bp),
                bg_color=pend_color,
                text_color=color.WHITE,
                font_size=9,
                callout_position=cp_pos,
            )
            self.chart.draw(ppl)
            prev_pend_label.set(ppl)

            has_pend_drawings.set(1)

        return


# ============================================================================
# HELPER FUNCTIONS (module-level, not methods)
# ============================================================================
def _calc_avg_body(ctx: MainContext, length: int) -> float:
    """Calculate average body size over `length` bars (manual SMA)."""
    total: float = 0.0
    count: int = min(length, ctx.bar_index + 1)
    for i in range(count):
        total += abs(ctx.close[i] - ctx.open[i])
    if count == 0:
        return 0.0
    return total / count

