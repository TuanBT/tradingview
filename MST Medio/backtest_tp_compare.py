"""
Backtest MST Medio — Compare multiple TP strategies
"""
import pandas as pd
import sys
sys.path.insert(0, '.')
from strategy_pa_break import find_swings

df = pd.read_csv('data/XAUUSD_M5.csv')
pivotLen = 5
impulseMult = 1.5
swings = find_swings(df, pivotLen)

O = df['Open'].values
H = df['High'].values
L = df['Low'].values
C = df['Close'].values
n = len(df)
dt = df['datetime'].values

swing_at_bar = {}
for s in swings:
    det_bar = s.bar_index + pivotLen
    if det_bar not in swing_at_bar:
        swing_at_bar[det_bar] = []
    swing_at_bar[det_bar].append(s)

# ---- Signal generation (same as before) ----
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
                avg_body = sum(abs(C[max(0, bar-20+j)] - O[max(0, bar-20+j)]) for j in range(20)) / 20
                from_bar = bar - sh0_idx
                found = False
                for i in range(from_bar, pivotLen - 1, -1):
                    if i < 0: continue
                    if C[bar-i] > sh0:
                        found = abs(C[bar-i] - O[bar-i]) >= impulseMult * avg_body
                        break
                if found and slBeforeSH is not None:
                    isNewHH = True

    isNewLL = False
    if bar in swing_at_bar:
        for s in swing_at_bar[bar]:
            if s.type == 'LOW' and sl0 is not None and sl1 < sl0:
                avg_body = sum(abs(C[max(0, bar-20+j)] - O[max(0, bar-20+j)]) for j in range(20)) / 20
                from_bar = bar - sl0_idx
                found = False
                for i in range(from_bar, pivotLen - 1, -1):
                    if i < 0: continue
                    if C[bar-i] < sl0:
                        found = abs(C[bar-i] - O[bar-i]) >= impulseMult * avg_body
                        break
                if found and shBeforeSL is not None:
                    isNewLL = True

    confirmedBuy = confirmedSell = False
    confEntry = confSL = confConfHigh = confConfLow = None
    confW1Peak = None

    if pendingState == 2 and pendBreakPoint is not None:
        if pendSL is not None and L[bar] <= pendSL:
            pendingState = 0
        elif L[bar] <= pendBreakPoint:
            confirmedBuy = True
            confEntry = pendBreakPoint; confSL = pendSL
            confConfHigh = waveConfHigh; confConfLow = waveConfLow
            confW1Peak = pendW1Peak
            pendingState = 0
        elif pendW1Trough is not None and L[bar] <= pendW1Trough:
            pendingState = 0

    if pendingState == -2 and pendBreakPoint is not None:
        if pendSL is not None and H[bar] >= pendSL:
            pendingState = 0
        elif H[bar] >= pendBreakPoint:
            confirmedSell = True
            confEntry = pendBreakPoint; confSL = pendSL
            confConfHigh = waveConfHigh; confConfLow = waveConfLow
            confW1Peak = pendW1Peak
            pendingState = 0
        elif pendW1Trough is not None and H[bar] >= pendW1Trough:
            pendingState = 0

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

    if isNewHH and pendingState != 2:
        _w1Peak = _w1Bar = _w1TroughInit = None; _foundBreak = False
        for i in range(bar - sh0_idx, -1, -1):
            cl, op, hi, lo = C[bar-i], O[bar-i], H[bar-i], L[bar-i]
            if not _foundBreak:
                if cl > sh0:
                    _foundBreak = True; _w1Peak = hi; _w1Bar = bar - i; _w1TroughInit = lo
            else:
                if hi > _w1Peak: _w1Peak = hi; _w1Bar = bar - i
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

    if isNewLL and pendingState != -2:
        _w1Trough = _w1BarSell = _w1TroughInitSell = None; _foundBrkDn = False
        for i in range(bar - sl0_idx, -1, -1):
            cl, op, lo, hi = C[bar-i], O[bar-i], L[bar-i], H[bar-i]
            if not _foundBrkDn:
                if cl < sl0:
                    _foundBrkDn = True; _w1Trough = lo; _w1BarSell = bar-i; _w1TroughInitSell = hi
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

# ---- Evaluate multiple TP strategies ----
def evaluate_tp(signals, tp_name, tp_func):
    wins = losses = 0
    total_r = 0.0
    details = []
    for sig in signals:
        entry = sig['entry']; sl = sig['sl']
        d = sig['dir']; sb = sig['signal_bar']
        
        if d == 'BUY':
            risk = entry - sl
            if risk <= 0: continue
            tp = tp_func(sig, risk, 'BUY')
            rr = (tp - entry) / risk
            result = None
            for j in range(sb + 1, n):
                if L[j] <= sl: result = 'SL'; break
                if H[j] >= tp: result = 'TP'; break
        else:
            risk = sl - entry
            if risk <= 0: continue
            tp = tp_func(sig, risk, 'SELL')
            rr = (entry - tp) / risk
            result = None
            for j in range(sb + 1, n):
                if H[j] >= sl: result = 'SL'; break
                if L[j] <= tp: result = 'TP'; break
        
        if result is None: r_val = 0
        elif result == 'TP': r_val = rr; wins += 1
        else: r_val = -1.0; losses += 1
        total_r += r_val
        details.append((sig['datetime'], d, entry, sl, tp, rr, result, r_val))
    
    total = wins + losses
    wr = (wins / total * 100) if total > 0 else 0
    return {'name': tp_name, 'signals': len(signals), 'closed': total,
            'wins': wins, 'losses': losses, 'wr': wr, 'total_r': total_r,
            'details': details}

# TP strategies
strategies = {
    'TP=Confirm Peak (no min)': lambda sig, risk, d: (
        sig['conf_high'] if d == 'BUY' else sig['conf_low']
    ),
    'TP=Confirm, min 1:1.5': lambda sig, risk, d: (
        max(sig['conf_high'], sig['entry'] + 1.5 * risk) if d == 'BUY'
        else min(sig['conf_low'], sig['entry'] - 1.5 * risk)
    ),
    'TP=Confirm, min 1:2': lambda sig, risk, d: (
        max(sig['conf_high'], sig['entry'] + 2 * risk) if d == 'BUY'
        else min(sig['conf_low'], sig['entry'] - 2 * risk)
    ),
    'TP=Confirm, min 1:3': lambda sig, risk, d: (
        max(sig['conf_high'], sig['entry'] + 3 * risk) if d == 'BUY'
        else min(sig['conf_low'], sig['entry'] - 3 * risk)
    ),
    'TP=W1 Peak': lambda sig, risk, d: (
        sig['w1_peak'] if d == 'BUY' else sig['w1_peak']
    ),
    'TP=W1 Peak, min 1:2': lambda sig, risk, d: (
        max(sig['w1_peak'], sig['entry'] + 2 * risk) if d == 'BUY'
        else min(sig['w1_peak'], sig['entry'] - 2 * risk)
    ),
    'Fixed 1:1': lambda sig, risk, d: (
        sig['entry'] + 1 * risk if d == 'BUY' else sig['entry'] - 1 * risk
    ),
    'Fixed 1:1.5': lambda sig, risk, d: (
        sig['entry'] + 1.5 * risk if d == 'BUY' else sig['entry'] - 1.5 * risk
    ),
    'Fixed 1:2': lambda sig, risk, d: (
        sig['entry'] + 2 * risk if d == 'BUY' else sig['entry'] - 2 * risk
    ),
    'Fixed 1:3': lambda sig, risk, d: (
        sig['entry'] + 3 * risk if d == 'BUY' else sig['entry'] - 3 * risk
    ),
    'Fixed 1:4': lambda sig, risk, d: (
        sig['entry'] + 4 * risk if d == 'BUY' else sig['entry'] - 4 * risk
    ),
    'Fixed 1:5': lambda sig, risk, d: (
        sig['entry'] + 5 * risk if d == 'BUY' else sig['entry'] - 5 * risk
    ),
}

# ---- Trailing Stop strategies ----
def evaluate_trailing(signals, name, initial_rr_lock, trail_step):
    """Trail SL after hitting initial_rr_lock, moving SL by trail_step increments"""
    wins = losses = 0; total_r = 0.0; details = []
    for sig in signals:
        entry = sig['entry']; sl = sig['sl']
        d = sig['dir']; sb = sig['signal_bar']
        if d == 'BUY':
            risk = entry - sl
            if risk <= 0: continue
        else:
            risk = sl - entry
            if risk <= 0: continue
        
        current_sl = sl
        best_r = 0.0
        result = None; final_r = 0
        for j in range(sb + 1, n):
            if d == 'BUY':
                if L[j] <= current_sl:
                    result = 'SL' if current_sl <= entry else 'TP'
                    final_r = (current_sl - entry) / risk
                    break
                curr_r = (H[j] - entry) / risk
                if curr_r > best_r:
                    best_r = curr_r
                    if best_r >= initial_rr_lock:
                        new_sl = entry + (best_r - trail_step) * risk
                        if new_sl > current_sl: current_sl = new_sl
            else:
                if H[j] >= current_sl:
                    result = 'SL' if current_sl >= entry else 'TP'
                    final_r = (entry - current_sl) / risk
                    break
                curr_r = (entry - L[j]) / risk
                if curr_r > best_r:
                    best_r = curr_r
                    if best_r >= initial_rr_lock:
                        new_sl = entry - (best_r - trail_step) * risk
                        if new_sl < current_sl: current_sl = new_sl
        
        if result is None: final_r = 0; result = 'OPEN'
        if result == 'SL' and current_sl == sl: final_r = -1.0
        total_r += final_r
        if result == 'TP' or (result == 'SL' and final_r > 0): wins += 1
        elif result == 'SL': losses += 1
        details.append((sig['datetime'], d, entry, sl, 0, best_r, result, final_r))
    
    total = wins + losses
    wr = (wins / total * 100) if total > 0 else 0
    return {'name': name, 'signals': len(signals), 'closed': total,
            'wins': wins, 'losses': losses, 'wr': wr, 'total_r': total_r,
            'details': details}

# ---- Break Even strategies ----
def evaluate_breakeven(signals, name, be_trigger_rr, tp_rr):
    """Move SL to breakeven (entry) when price reaches be_trigger_rr, TP at tp_rr"""
    wins = losses = 0; total_r = 0.0; details = []
    for sig in signals:
        entry = sig['entry']; sl = sig['sl']
        d = sig['dir']; sb = sig['signal_bar']
        if d == 'BUY':
            risk = entry - sl
            if risk <= 0: continue
            tp = entry + tp_rr * risk
        else:
            risk = sl - entry
            if risk <= 0: continue
            tp = entry - tp_rr * risk
        
        current_sl = sl; triggered_be = False
        result = None; rr = tp_rr
        for j in range(sb + 1, n):
            if d == 'BUY':
                if not triggered_be and H[j] >= entry + be_trigger_rr * risk:
                    triggered_be = True; current_sl = entry
                if L[j] <= current_sl:
                    result = 'BE' if triggered_be and current_sl == entry else 'SL'
                    break
                if H[j] >= tp: result = 'TP'; break
            else:
                if not triggered_be and L[j] <= entry - be_trigger_rr * risk:
                    triggered_be = True; current_sl = entry
                if H[j] >= current_sl:
                    result = 'BE' if triggered_be and current_sl == entry else 'SL'
                    break
                if L[j] <= tp: result = 'TP'; break
        
        if result == 'TP': r_val = rr; wins += 1
        elif result == 'BE': r_val = 0.0
        elif result == 'SL': r_val = -1.0; losses += 1
        else: r_val = 0.0
        total_r += r_val
        details.append((sig['datetime'], d, entry, sl, tp, rr, result, r_val))
    
    total = wins + losses
    wr = (wins / total * 100) if total > 0 else 0
    return {'name': name, 'signals': len(signals), 'closed': total,
            'wins': wins, 'losses': losses, 'wr': wr, 'total_r': total_r,
            'details': details}

print("=" * 90)
print(f"{'TP Strategy':<30} {'Signals':>8} {'Wins':>6} {'Loss':>6} {'WR%':>8} {'Total R':>10} {'Avg R':>8}")
print("=" * 90)

results = []
for name, func in strategies.items():
    r = evaluate_tp(signals, name, func)
    results.append(r)
    avg_r = r['total_r'] / r['closed'] if r['closed'] > 0 else 0
    print(f"{r['name']:<30} {r['signals']:>8} {r['wins']:>6} {r['losses']:>6} {r['wr']:>7.1f}% {r['total_r']:>+10.2f} {avg_r:>+8.3f}")

print("-" * 90)
print(f"{'[Break Even Strategies]':<30}")
print("-" * 90)

be_strategies = [
    ('BE@1R → TP 1:2', 1.0, 2.0),
    ('BE@1R → TP 1:3', 1.0, 3.0),
    ('BE@1R → TP 1:4', 1.0, 4.0),
    ('BE@0.5R → TP 1:2', 0.5, 2.0),
    ('BE@0.5R → TP 1:3', 0.5, 3.0),
]
for name, be_tr, tp_rr in be_strategies:
    r = evaluate_breakeven(signals, name, be_tr, tp_rr)
    results.append(r)
    be_count = sum(1 for d in r['details'] if d[6] == 'BE')
    avg_r = r['total_r'] / r['closed'] if r['closed'] > 0 else 0
    print(f"{r['name']:<30} {r['signals']:>8} {r['wins']:>6} {r['losses']:>6} {r['wr']:>7.1f}% {r['total_r']:>+10.2f} {avg_r:>+8.3f}  (BE:{be_count})")

print("-" * 90)
print(f"{'[Trailing Stop Strategies]':<30}")
print("-" * 90)

trail_strategies = [
    ('Trail: lock@1R, step=0.5R', 1.0, 0.5),
    ('Trail: lock@1R, step=1R', 1.0, 1.0),
    ('Trail: lock@1.5R, step=0.5R', 1.5, 0.5),
    ('Trail: lock@1.5R, step=1R', 1.5, 1.0),
    ('Trail: lock@0.5R, step=0.5R', 0.5, 0.5),
]
for name, lock, step in trail_strategies:
    r = evaluate_trailing(signals, name, lock, step)
    results.append(r)
    avg_r = r['total_r'] / r['closed'] if r['closed'] > 0 else 0
    print(f"{r['name']:<30} {r['signals']:>8} {r['wins']:>6} {r['losses']:>6} {r['wr']:>7.1f}% {r['total_r']:>+10.2f} {avg_r:>+8.3f}")

print("=" * 90)

# Show best strategy details
best = max(results, key=lambda x: x['total_r'])
print(f"\n🏆 Best by Total R: {best['name']} ({best['wr']:.1f}% WR, {best['total_r']:+.2f}R)")
print()

# Show details for best strategy
print(f"{'Datetime':<26} {'Dir':>4} {'Entry':>10} {'SL':>10} {'TP':>10} {'RR':>6} {'Result':>8} {'R':>6}")
print("-" * 90)
for d in best['details']:
    dtime, direction, entry, sl, tp, rr, result, r_val = d
    print(f"{dtime:<26} {direction:>4} {entry:>10.3f} {sl:>10.3f} {tp:>10.3f} {rr:>6.2f} {result or 'OPEN':>8} {r_val:>+6.2f}")
print("-" * 90)
