"""
Backtest MST Medio — Multi-timeframe TP comparison
M5  : 5000 bars (~26 ngày, Jan 15 → Feb 10 2026)
M15 : 5000 bars (~81 ngày, Nov 21 2025 → Feb 10 2026)
"""
import pandas as pd
import sys
sys.path.insert(0, '.')
from strategy_pa_break import find_swings

# ─── Signal Generator ───
def generate_signals(df, pivotLen=5, impulseMult=1.5):
    O = df['Open'].values; H = df['High'].values
    L = df['Low'].values; C = df['Close'].values
    n = len(df); dt = df['datetime'].values

    swings = find_swings(df, pivotLen)
    swing_at_bar = {}
    for s in swings:
        det_bar = s.bar_index + pivotLen
        if det_bar not in swing_at_bar: swing_at_bar[det_bar] = []
        swing_at_bar[det_bar].append(s)

    sh1 = sh0 = sh1_idx = sh0_idx = None
    sl1 = sl0 = sl1_idx = sl0_idx = None
    slBeforeSH = slBeforeSH_idx = None
    shBeforeSL = shBeforeSL_idx = None
    pendingState = 0
    pendBreakPoint = pendW1Peak = pendW1Trough = pendSL = None
    waveConfBar = waveConfHigh = waveConfLow = None
    signals = []

    for bar in range(n):
        if bar in swing_at_bar:
            for s in swing_at_bar[bar]:
                if s.type == 'LOW':
                    sl0, sl0_idx = sl1, sl1_idx
                    sl1, sl1_idx = s.price, s.bar_index
            for s in swing_at_bar[bar]:
                if s.type == 'HIGH':
                    slBeforeSH, slBeforeSH_idx = sl1, sl1_idx
                    sh0, sh0_idx = sh1, sh1_idx
                    sh1, sh1_idx = s.price, s.bar_index
            for s in swing_at_bar[bar]:
                if s.type == 'LOW':
                    shBeforeSL, shBeforeSL_idx = sh1, sh1_idx

        isNewHH = False
        if bar in swing_at_bar:
            for s in swing_at_bar[bar]:
                if s.type == 'HIGH' and sh0 is not None and sh1 > sh0:
                    avg_body = sum(abs(C[max(0,bar-20+j)] - O[max(0,bar-20+j)]) for j in range(20)) / 20
                    from_bar = bar - sh0_idx; found = False
                    for i in range(from_bar, pivotLen-1, -1):
                        if i < 0: continue
                        if C[bar-i] > sh0:
                            found = abs(C[bar-i] - O[bar-i]) >= impulseMult * avg_body; break
                    if found and slBeforeSH is not None: isNewHH = True

        isNewLL = False
        if bar in swing_at_bar:
            for s in swing_at_bar[bar]:
                if s.type == 'LOW' and sl0 is not None and sl1 < sl0:
                    avg_body = sum(abs(C[max(0,bar-20+j)] - O[max(0,bar-20+j)]) for j in range(20)) / 20
                    from_bar = bar - sl0_idx; found = False
                    for i in range(from_bar, pivotLen-1, -1):
                        if i < 0: continue
                        if C[bar-i] < sl0:
                            found = abs(C[bar-i] - O[bar-i]) >= impulseMult * avg_body; break
                    if found and shBeforeSL is not None: isNewLL = True

        confirmedBuy = confirmedSell = False
        confEntry = confSL = confConfHigh = confConfLow = confW1Peak = None

        if pendingState == 2 and pendBreakPoint is not None:
            if pendSL is not None and L[bar] <= pendSL: pendingState = 0
            elif L[bar] <= pendBreakPoint:
                confirmedBuy = True; confEntry = pendBreakPoint; confSL = pendSL
                confConfHigh = waveConfHigh; confConfLow = waveConfLow; confW1Peak = pendW1Peak; pendingState = 0
            elif pendW1Trough is not None and L[bar] <= pendW1Trough: pendingState = 0

        if pendingState == -2 and pendBreakPoint is not None:
            if pendSL is not None and H[bar] >= pendSL: pendingState = 0
            elif H[bar] >= pendBreakPoint:
                confirmedSell = True; confEntry = pendBreakPoint; confSL = pendSL
                confConfHigh = waveConfHigh; confConfLow = waveConfLow; confW1Peak = pendW1Peak; pendingState = 0
            elif pendW1Trough is not None and H[bar] >= pendW1Trough: pendingState = 0

        if pendingState == 1:
            if pendW1Trough is None or L[bar] < pendW1Trough: pendW1Trough = L[bar]
            if pendSL is not None and L[bar] <= pendSL: pendingState = 0
            elif pendBreakPoint is not None and L[bar] <= pendBreakPoint: pendingState = 0
            elif pendW1Peak is not None and C[bar] > pendW1Peak:
                pendingState = 2; waveConfBar = bar; waveConfHigh = H[bar]; waveConfLow = L[bar]

        if pendingState == -1:
            if pendW1Trough is None or H[bar] > pendW1Trough: pendW1Trough = H[bar]
            if pendSL is not None and H[bar] >= pendSL: pendingState = 0
            elif pendBreakPoint is not None and H[bar] >= pendBreakPoint: pendingState = 0
            elif pendW1Peak is not None and C[bar] < pendW1Peak:
                pendingState = -2; waveConfBar = bar; waveConfHigh = H[bar]; waveConfLow = L[bar]

        # rawBreakUp
        if isNewHH and pendingState != 2:
            _w1Peak = _w1Bar = _w1TroughInit = None; _foundBreak = False
            for i in range(bar - sh0_idx, -1, -1):
                cl, op, hi, lo = C[bar-i], O[bar-i], H[bar-i], L[bar-i]
                if not _foundBreak:
                    if cl > sh0: _foundBreak = True; _w1Peak = hi; _w1Bar = bar-i; _w1TroughInit = lo
                else:
                    if hi > _w1Peak: _w1Peak = hi; _w1Bar = bar-i
                    if _w1TroughInit is None or lo < _w1TroughInit: _w1TroughInit = lo
                    if cl < op: break
            if _w1Peak is not None:
                pendingState = 1; pendBreakPoint = sh0; pendW1Peak = _w1Peak
                pendW1Trough = _w1TroughInit; pendSL = slBeforeSH
                retro_from = max((bar - _w1Bar) - 1, 0)
                for i in range(retro_from, -1, -1):
                    rH, rL, rC = H[bar-i], L[bar-i], C[bar-i]
                    if pendingState == 1:
                        if pendW1Trough is None or rL < pendW1Trough: pendW1Trough = rL
                        if pendSL is not None and rL <= pendSL: pendingState = 0; break
                        if rL <= pendBreakPoint: pendingState = 0; break
                        if rC > pendW1Peak:
                            pendingState = 2; waveConfBar = bar-i; waveConfHigh = rH; waveConfLow = rL; continue
                    if pendingState == 2:
                        if pendSL is not None and rL <= pendSL: pendingState = 0; break
                        if rL <= pendBreakPoint:
                            confirmedBuy = True; confEntry = pendBreakPoint; confSL = pendSL
                            confConfHigh = waveConfHigh; confConfLow = waveConfLow; confW1Peak = pendW1Peak
                            pendingState = 0; break
                        if pendW1Trough is not None and rL <= pendW1Trough: pendingState = 0; break
                    if pendingState == 0: break

        # rawBreakDown
        if isNewLL and pendingState != -2:
            _w1Trough = _w1BarSell = _w1TroughInitSell = None; _foundBrkDn = False
            for i in range(bar - sl0_idx, -1, -1):
                cl, op, lo, hi = C[bar-i], O[bar-i], L[bar-i], H[bar-i]
                if not _foundBrkDn:
                    if cl < sl0: _foundBrkDn = True; _w1Trough = lo; _w1BarSell = bar-i; _w1TroughInitSell = hi
                else:
                    if lo < _w1Trough: _w1Trough = lo; _w1BarSell = bar-i
                    if _w1TroughInitSell is None or hi > _w1TroughInitSell: _w1TroughInitSell = hi
                    if cl > op: break
            if _w1Trough is not None:
                pendingState = -1; pendBreakPoint = sl0; pendW1Peak = _w1Trough
                pendW1Trough = _w1TroughInitSell; pendSL = shBeforeSL
                retro_from = max((bar - _w1BarSell) - 1, 0)
                for i in range(retro_from, -1, -1):
                    rH, rL, rC = H[bar-i], L[bar-i], C[bar-i]
                    if pendingState == -1:
                        if pendW1Trough is None or rH > pendW1Trough: pendW1Trough = rH
                        if pendSL is not None and rH >= pendSL: pendingState = 0; break
                        if rH >= pendBreakPoint: pendingState = 0; break
                        if rC < pendW1Peak:
                            pendingState = -2; waveConfBar = bar-i; waveConfHigh = rH; waveConfLow = rL; continue
                    if pendingState == -2:
                        if pendSL is not None and rH >= pendSL: pendingState = 0; break
                        if rH >= pendBreakPoint:
                            confirmedSell = True; confEntry = pendBreakPoint; confSL = pendSL
                            confConfHigh = waveConfHigh; confConfLow = waveConfLow; confW1Peak = pendW1Peak
                            pendingState = 0; break
                        if pendW1Trough is not None and rH >= pendW1Trough: pendingState = 0; break
                    if pendingState == 0: break

        if confirmedBuy:
            signals.append({'datetime': str(dt[bar])[:22], 'dir': 'BUY', 'entry': confEntry,
                'sl': confSL, 'conf_high': confConfHigh, 'conf_low': confConfLow,
                'w1_peak': confW1Peak, 'signal_bar': bar})
        if confirmedSell:
            signals.append({'datetime': str(dt[bar])[:22], 'dir': 'SELL', 'entry': confEntry,
                'sl': confSL, 'conf_high': confConfHigh, 'conf_low': confConfLow,
                'w1_peak': confW1Peak, 'signal_bar': bar})

    return signals, H, L, C, n

# ─── TP Evaluators ───
def eval_fixed_tp(signals, H, L, C, n, rr_target):
    wins = losses = 0; total_r = 0.0
    for sig in signals:
        entry, sl, d, sb = sig['entry'], sig['sl'], sig['dir'], sig['signal_bar']
        risk = (entry - sl) if d == 'BUY' else (sl - entry)
        if risk <= 0: continue
        tp = (entry + rr_target * risk) if d == 'BUY' else (entry - rr_target * risk)
        result = None
        for j in range(sb + 1, n):
            if d == 'BUY':
                if L[j] <= sl: result = 'SL'; break
                if H[j] >= tp: result = 'TP'; break
            else:
                if H[j] >= sl: result = 'SL'; break
                if L[j] <= tp: result = 'TP'; break
        if result == 'TP': wins += 1; total_r += rr_target
        elif result == 'SL': losses += 1; total_r -= 1.0
    return wins, losses, total_r

def eval_structure_tp(signals, H, L, C, n, key, min_rr=0):
    """key = 'w1_peak' or 'conf_high'/'conf_low'"""
    wins = losses = 0; total_r = 0.0
    for sig in signals:
        entry, sl, d, sb = sig['entry'], sig['sl'], sig['dir'], sig['signal_bar']
        risk = (entry - sl) if d == 'BUY' else (sl - entry)
        if risk <= 0: continue
        if d == 'BUY':
            natural = sig.get('w1_peak', sig['conf_high']) if key == 'w1_peak' else sig['conf_high']
            tp = max(natural, entry + min_rr * risk) if min_rr > 0 else natural
        else:
            natural = sig.get('w1_peak', sig['conf_low']) if key == 'w1_peak' else sig['conf_low']
            tp = min(natural, entry - min_rr * risk) if min_rr > 0 else natural
        rr = abs(tp - entry) / risk
        result = None
        for j in range(sb + 1, n):
            if d == 'BUY':
                if L[j] <= sl: result = 'SL'; break
                if H[j] >= tp: result = 'TP'; break
            else:
                if H[j] >= sl: result = 'SL'; break
                if L[j] <= tp: result = 'TP'; break
        if result == 'TP': wins += 1; total_r += rr
        elif result == 'SL': losses += 1; total_r -= 1.0
    return wins, losses, total_r

def eval_trailing(signals, H, L, C, n, lock_rr, step):
    wins = losses = 0; total_r = 0.0
    for sig in signals:
        entry, sl, d, sb = sig['entry'], sig['sl'], sig['dir'], sig['signal_bar']
        risk = (entry - sl) if d == 'BUY' else (sl - entry)
        if risk <= 0: continue
        current_sl = sl; best_r = 0.0; result = None; final_r = 0
        for j in range(sb + 1, n):
            if d == 'BUY':
                if L[j] <= current_sl:
                    result = 'SL' if current_sl <= entry else 'TP'
                    final_r = (current_sl - entry) / risk; break
                curr_r = (H[j] - entry) / risk
                if curr_r > best_r:
                    best_r = curr_r
                    if best_r >= lock_rr:
                        new_sl = entry + (best_r - step) * risk
                        if new_sl > current_sl: current_sl = new_sl
            else:
                if H[j] >= current_sl:
                    result = 'SL' if current_sl >= entry else 'TP'
                    final_r = (entry - current_sl) / risk; break
                curr_r = (entry - L[j]) / risk
                if curr_r > best_r:
                    best_r = curr_r
                    if best_r >= lock_rr:
                        new_sl = entry - (best_r - step) * risk
                        if new_sl < current_sl: current_sl = new_sl
        if result is None: continue
        if result == 'SL' and current_sl == sl: final_r = -1.0
        total_r += final_r
        if final_r > 0: wins += 1
        elif final_r < 0: losses += 1
    return wins, losses, total_r

def eval_be(signals, H, L, C, n, be_trigger, tp_rr):
    wins = losses = be_count = 0; total_r = 0.0
    for sig in signals:
        entry, sl, d, sb = sig['entry'], sig['sl'], sig['dir'], sig['signal_bar']
        risk = (entry - sl) if d == 'BUY' else (sl - entry)
        if risk <= 0: continue
        tp = (entry + tp_rr * risk) if d == 'BUY' else (entry - tp_rr * risk)
        current_sl = sl; triggered = False; result = None
        for j in range(sb + 1, n):
            if d == 'BUY':
                if not triggered and H[j] >= entry + be_trigger * risk: triggered = True; current_sl = entry
                if L[j] <= current_sl:
                    result = 'BE' if triggered and current_sl == entry else 'SL'; break
                if H[j] >= tp: result = 'TP'; break
            else:
                if not triggered and L[j] <= entry - be_trigger * risk: triggered = True; current_sl = entry
                if H[j] >= current_sl:
                    result = 'BE' if triggered and current_sl == entry else 'SL'; break
                if L[j] <= tp: result = 'TP'; break
        if result == 'TP': wins += 1; total_r += tp_rr
        elif result == 'BE': be_count += 1
        elif result == 'SL': losses += 1; total_r -= 1.0
    return wins, losses, be_count, total_r

# ─── Run on both datasets ───
datasets = [
    ('M5  (26d)', 'data/XAUUSD_M5.csv'),
    ('M15 (81d)', 'data/XAUUSD_M15.csv'),
]

for ds_name, ds_path in datasets:
    df = pd.read_csv(ds_path)
    signals, H, L, C, n = generate_signals(df)
    
    print(f"\n{'='*95}")
    print(f"  📊 {ds_name} — {len(df)} bars — {len(signals)} signals")
    print(f"{'='*95}")
    print(f"{'Strategy':<35} {'Win':>5} {'Loss':>5} {'WR%':>7} {'Total R':>10} {'Avg R/trade':>12}")
    print(f"{'-'*95}")
    
    # Fixed TP
    print("  [Fixed RR]")
    for rr in [1.0, 1.5, 2.0, 3.0, 4.0, 5.0]:
        w, l, tr = eval_fixed_tp(signals, H, L, C, n, rr)
        total = w + l; wr = (w/total*100) if total > 0 else 0
        avg = tr / total if total > 0 else 0
        print(f"    Fixed 1:{rr:<4.1f}                       {w:>5} {l:>5} {wr:>6.1f}% {tr:>+10.2f} {avg:>+12.3f}")
    
    # Structure TP
    print("  [Structure TP]")
    for name, key, min_rr in [
        ('W1 Peak', 'w1_peak', 0),
        ('W1 Peak, min 1:2', 'w1_peak', 2),
        ('Confirm Peak', 'conf_high', 0),
        ('Confirm Peak, min 1:2', 'conf_high', 2),
    ]:
        w, l, tr = eval_structure_tp(signals, H, L, C, n, key, min_rr)
        total = w + l; wr = (w/total*100) if total > 0 else 0
        avg = tr / total if total > 0 else 0
        print(f"    {name:<31}   {w:>5} {l:>5} {wr:>6.1f}% {tr:>+10.2f} {avg:>+12.3f}")
    
    # Trailing
    print("  [Trailing Stop]")
    for name, lock, step in [
        ('Trail lock@0.5R step=0.5R', 0.5, 0.5),
        ('Trail lock@1R step=0.5R', 1.0, 0.5),
        ('Trail lock@1R step=1R', 1.0, 1.0),
        ('Trail lock@1.5R step=0.5R', 1.5, 0.5),
    ]:
        w, l, tr = eval_trailing(signals, H, L, C, n, lock, step)
        total = w + l; wr = (w/total*100) if total > 0 else 0
        avg = tr / total if total > 0 else 0
        print(f"    {name:<31}   {w:>5} {l:>5} {wr:>6.1f}% {tr:>+10.2f} {avg:>+12.3f}")
    
    # Break Even
    print("  [Break Even]")
    for name, be_tr, tp_rr in [
        ('BE@0.5R → TP 1:2', 0.5, 2.0),
        ('BE@1R → TP 1:2', 1.0, 2.0),
        ('BE@1R → TP 1:3', 1.0, 3.0),
        ('BE@1R → TP 1:4', 1.0, 4.0),
    ]:
        w, l, be, tr = eval_be(signals, H, L, C, n, be_tr, tp_rr)
        total = w + l; wr = (w/total*100) if total > 0 else 0
        avg = tr / (w + l + be) if (w + l + be) > 0 else 0
        print(f"    {name:<31}   {w:>5} {l:>5} {wr:>6.1f}% {tr:>+10.2f} {avg:>+12.3f}  (BE:{be})")

    print(f"{'-'*95}")

    # Signal list summary
    buy_count = sum(1 for s in signals if s['dir'] == 'BUY')
    sell_count = sum(1 for s in signals if s['dir'] == 'SELL')
    print(f"  Signals: {len(signals)} (BUY:{buy_count} SELL:{sell_count})")
    print(f"  First: {signals[0]['datetime'] if signals else 'N/A'}")
    print(f"  Last:  {signals[-1]['datetime'] if signals else 'N/A'}")
    
    # Show all signals with W1 Peak natural RR
    print(f"\n  {'#':>3} {'Datetime':<24} {'Dir':>4} {'Entry':>10} {'SL':>10} {'Risk':>8} {'W1 Peak':>10} {'W1 RR':>6}")
    for i, sig in enumerate(signals, 1):
        entry, sl, d = sig['entry'], sig['sl'], sig['dir']
        risk = (entry - sl) if d == 'BUY' else (sl - entry)
        w1 = sig.get('w1_peak', 0)
        w1_rr = abs(w1 - entry) / risk if risk > 0 else 0
        print(f"  {i:>3} {sig['datetime']:<24} {d:>4} {entry:>10.3f} {sl:>10.3f} {risk:>8.3f} {w1:>10.3f} {w1_rr:>6.2f}")
